from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router as api_router
from app.config import Settings, get_settings
from app.github_api.client import GitHubClient
from app.jobs import JobStore
from app.repos.store import RepoStore
from app.review.llm import LLMClient
from app.review.registry import AgentRegistry
from app.webhooks.github import router as webhook_router

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    github: GitHubClient | None = None,
    llm: LLMClient | None = None,
    repo_store: RepoStore | None = None,
    jobs: JobStore | None = None,
    registry: AgentRegistry | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    jobs = jobs or JobStore()
    repo_store = repo_store or RepoStore(settings.repos_file)
    github = github or GitHubClient(
        settings.github_token, base_url=settings.github_api_base
    )
    llm = llm or LLMClient(settings)
    registry = registry or AgentRegistry(
        repo_store,
        settings=settings,
        github=github,
        llm=llm,
        jobs=jobs,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        names = [record.repo for record in registry.list_records()]
        logger.info("Loaded %s review agent(s): %s", len(names), names)
        yield
        await github.aclose()
        await llm.aclose()

    app = FastAPI(title="Peearh", lifespan=lifespan)
    app.state.settings = settings
    app.state.jobs = jobs
    app.state.github = github
    app.state.llm = llm
    app.state.repo_store = repo_store
    app.state.registry = registry
    app.include_router(api_router)
    app.include_router(webhook_router)
    return app
