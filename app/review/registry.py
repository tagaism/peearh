from __future__ import annotations

from app.config import Settings
from app.github_api.client import GitHubClient
from app.jobs import JobStore
from app.repos.models import RepoRecord
from app.repos.store import RepoStore
from app.review.agent import ReviewAgent
from app.review.llm import LLMClient


class AgentRegistry:
    """Creates and holds one ReviewAgent per registered repository."""

    def __init__(
        self,
        store: RepoStore,
        *,
        settings: Settings,
        github: GitHubClient,
        llm: LLMClient,
        jobs: JobStore,
    ) -> None:
        self.store = store
        self.settings = settings
        self.github = github
        self.llm = llm
        self.jobs = jobs
        self._agents: dict[str, ReviewAgent] = {}
        for record in store.list():
            self._put(record)

    def list_records(self) -> list[RepoRecord]:
        return self.store.list()

    def get(self, full_name: str) -> ReviewAgent | None:
        return self._agents.get(full_name.lower())

    def register(
        self,
        *,
        repo: str,
        name: str = "",
        description: str = "",
        review_focus: str = "",
    ) -> ReviewAgent:
        record = self.store.upsert(
            repo=repo,
            name=name,
            description=description,
            review_focus=review_focus,
        )
        return self._put(record)

    def _put(self, record: RepoRecord) -> ReviewAgent:
        agent = ReviewAgent(
            record,
            settings=self.settings,
            github=self.github,
            llm=self.llm,
            jobs=self.jobs,
        )
        self._agents[record.repo.lower()] = agent
        return agent
