from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from app.jobs import JobStore
from app.repos.models import RepoCreate
from app.review.llm import LLMError
from app.review.registry import AgentRegistry

router = APIRouter()

_STATIC = Path(__file__).resolve().parent / "static" / "index.html"


def _state(request: Request):
    return request.app.state


@router.get("/")
async def ui() -> FileResponse:
    return FileResponse(_STATIC, media_type="text/html")


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/llm")
async def health_llm(request: Request) -> dict[str, object]:
    try:
        models = await _state(request).llm.list_models()
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"status": "ok", "models": models}


@router.get("/jobs")
async def list_jobs(request: Request) -> dict:
    jobs: JobStore = _state(request).jobs
    return {"jobs": [job.to_dict() for job in jobs.list()]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    jobs: JobStore = _state(request).jobs
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@router.get("/repos")
async def list_repos(request: Request) -> dict:
    registry: AgentRegistry = _state(request).registry
    return {
        "repos": [
            {
                "repo": record.repo,
                "name": record.display_name,
                "description": record.description,
                "review_focus": record.review_focus,
            }
            for record in registry.list_records()
        ]
    }


@router.get("/repos/{owner}/{name}")
async def get_repo(owner: str, name: str, request: Request) -> dict:
    registry: AgentRegistry = _state(request).registry
    agent = registry.get(f"{owner}/{name}")
    if agent is None:
        raise HTTPException(status_code=404, detail="no agent for this repo")
    record = agent.record
    return {
        "repo": record.repo,
        "name": record.display_name,
        "description": record.description,
        "review_focus": record.review_focus,
    }


@router.post("/repos", status_code=201)
async def create_repo(body: RepoCreate, request: Request) -> dict:
    registry: AgentRegistry = _state(request).registry
    agent = registry.register(
        repo=body.repo,
        name=body.name,
        description=body.description,
        review_focus=body.review_focus,
    )
    record = agent.record
    return {
        "repo": record.repo,
        "name": record.display_name,
        "description": record.description,
        "review_focus": record.review_focus,
    }
