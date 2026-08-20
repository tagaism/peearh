from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.jobs import Job, JobStatus, JobStore
from app.review.registry import AgentRegistry
from app.webhooks.signatures import verify_signature

logger = logging.getLogger(__name__)

REVIEW_ACTIONS = {"opened", "ready_for_review", "synchronize"}

router = APIRouter()


def _state(request: Request) -> Any:
    return request.app.state


@router.post("/webhooks/github")
async def github_webhook(request: Request) -> JSONResponse:
    settings = _state(request).settings
    jobs: JobStore = _state(request).jobs
    registry: AgentRegistry = _state(request).registry

    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not verify_signature(
        secret=settings.github_webhook_secret,
        body=raw,
        header=signature,
    ):
        return JSONResponse({"detail": "invalid signature"}, status_code=401)

    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")

    if event == "ping":
        return JSONResponse({"status": "pong"})

    if event != "pull_request":
        return JSONResponse(
            {"status": "ignored", "reason": f"unsupported event: {event}"}
        )

    if delivery_id:
        existing = jobs.find_delivery(delivery_id)
        if existing:
            return JSONResponse(
                {"status": "duplicate", "job_id": existing.id},
                status_code=202,
            )

    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return JSONResponse({"detail": "invalid JSON"}, status_code=400)

    return await _handle_pull_request(
        payload, delivery_id=delivery_id, jobs=jobs, registry=registry
    )


async def _handle_pull_request(
    payload: dict[str, Any],
    *,
    delivery_id: str,
    jobs: JobStore,
    registry: AgentRegistry,
) -> JSONResponse:
    action = payload.get("action") or ""
    repo_full = (payload.get("repository") or {}).get("full_name") or ""
    pull = payload.get("pull_request") or {}
    pr_number = pull.get("number")
    head_sha = (pull.get("head") or {}).get("sha")
    draft = bool(pull.get("draft"))

    if action not in REVIEW_ACTIONS:
        job = jobs.create(
            repo=repo_full or "unknown",
            pr_number=pr_number,
            head_sha=head_sha,
            delivery_id=delivery_id or None,
            action=action,
            status=JobStatus.IGNORED,
            reason=f"action {action!r} is not reviewed",
        )
        return JSONResponse(job.to_dict(), status_code=202)

    if draft:
        job = jobs.create(
            repo=repo_full,
            pr_number=pr_number,
            head_sha=head_sha,
            delivery_id=delivery_id or None,
            action=action,
            status=JobStatus.IGNORED,
            reason="draft pull request",
        )
        return JSONResponse(job.to_dict(), status_code=202)

    if not repo_full or pr_number is None:
        return JSONResponse({"detail": "malformed pull_request payload"}, status_code=400)

    agent = registry.get(repo_full)
    if agent is None:
        if not registry.settings.allow_unregistered:
            job = jobs.create(
                repo=repo_full,
                pr_number=pr_number,
                head_sha=head_sha,
                delivery_id=delivery_id or None,
                action=action,
                status=JobStatus.IGNORED,
                reason=f"no agent registered for {repo_full}",
            )
            return JSONResponse(job.to_dict(), status_code=202)
        info = await _maybe_fetch_repo_brief(registry, repo_full)
        agent = registry.register(
            repo=repo_full,
            name=info.get("name") or repo_full.split("/")[-1],
            description=info.get("description") or "",
        )

    if head_sha:
        prior = jobs.find_review(repo_full, int(pr_number), head_sha)
        if prior and prior.status in {
            JobStatus.ACCEPTED,
            JobStatus.RUNNING,
            JobStatus.DONE,
        }:
            job = jobs.create(
                repo=repo_full,
                pr_number=int(pr_number),
                head_sha=head_sha,
                delivery_id=delivery_id or None,
                action=action,
                status=JobStatus.DUPLICATE,
                reason=f"already handled by job {prior.id}",
            )
            return JSONResponse(job.to_dict(), status_code=202)

    job = jobs.create(
        repo=repo_full,
        pr_number=int(pr_number),
        head_sha=head_sha,
        delivery_id=delivery_id or None,
        action=action,
        status=JobStatus.ACCEPTED,
    )
    asyncio.create_task(_run_review(agent.review_pr, job))
    return JSONResponse(job.to_dict(), status_code=202)


async def _maybe_fetch_repo_brief(
    registry: AgentRegistry, repo_full: str
) -> dict[str, str]:
    owner, name = repo_full.split("/", 1)
    try:
        info = await registry.github.get_repo(owner, name)
    except Exception:
        logger.exception("Failed to fetch repo info for %s", repo_full)
        return {}
    description = info.description or ""
    if info.language:
        extra = f"Primary language: {info.language}."
        description = f"{description} {extra}".strip()
    return {"name": name, "description": description}


async def _run_review(review_pr, job: Job) -> None:
    try:
        await review_pr(job)
    except Exception:
        logger.exception("Unhandled review error job=%s", job.id)
