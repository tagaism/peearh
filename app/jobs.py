from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    IGNORED = "ignored"
    DUPLICATE = "duplicate"


@dataclass
class JobEvent:
    kind: str
    message: str
    detail: str = ""
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "message": self.message,
            "detail": self.detail,
            "at": self.at.isoformat(),
        }


@dataclass
class Job:
    id: str
    status: JobStatus
    repo: str
    pr_number: int | None = None
    head_sha: str | None = None
    delivery_id: str | None = None
    action: str | None = None
    reason: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    events: list[JobEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_event(self, kind: str, message: str, detail: str = "") -> None:
        if len(detail) > 20_000:
            detail = detail[:20_000] + "\n…(truncated)"
        self.events.append(JobEvent(kind=kind, message=message, detail=detail))
        if len(self.events) > 200:
            self.events = self.events[-200:]
        self.updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status.value,
            "repo": self.repo,
            "pr_number": self.pr_number,
            "head_sha": self.head_sha,
            "delivery_id": self.delivery_id,
            "action": self.action,
            "reason": self.reason,
            "error": self.error,
            "result": self.result,
            "events": [event.to_dict() for event in self.events],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._deliveries: dict[str, str] = {}
        self._reviews: dict[tuple[str, int, str], str] = {}

    def create(
        self,
        *,
        repo: str,
        pr_number: int | None = None,
        head_sha: str | None = None,
        delivery_id: str | None = None,
        action: str | None = None,
        status: JobStatus = JobStatus.ACCEPTED,
        reason: str | None = None,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            status=status,
            repo=repo,
            pr_number=pr_number,
            head_sha=head_sha,
            delivery_id=delivery_id,
            action=action,
            reason=reason,
        )
        self._jobs[job.id] = job
        if delivery_id:
            self._deliveries[delivery_id] = job.id
        if pr_number is not None and head_sha:
            self._reviews[(repo, pr_number, head_sha)] = job.id
        label = f"{repo}"
        if pr_number is not None:
            label += f"#{pr_number}"
        job.add_event(
            status.value,
            f"{status.value}: {label}"
            + (f" ({action})" if action else "")
            + (f" — {reason}" if reason else ""),
        )
        return job

    def list(self, limit: int = 50) -> list[Job]:
        jobs = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        return jobs[:limit]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def find_delivery(self, delivery_id: str) -> Job | None:
        job_id = self._deliveries.get(delivery_id)
        return self._jobs.get(job_id) if job_id else None

    def find_review(self, repo: str, pr_number: int, head_sha: str) -> Job | None:
        job_id = self._reviews.get((repo, pr_number, head_sha))
        return self._jobs.get(job_id) if job_id else None

    def update(self, job: Job, **changes: Any) -> Job:
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc)
        return job
