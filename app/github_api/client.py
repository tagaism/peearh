from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.github_api.models import (
    CreatedReview,
    GitHubPullPayload,
    PullFile,
    PullRequest,
    RepoInfo,
    ReviewComment,
)

logger = logging.getLogger(__name__)

_API_VERSION = "2022-11-28"


class GitHubError(Exception):
    def __init__(self, status_code: int, message: str, body: str = "") -> None:
        super().__init__(f"GitHub API {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class GitHubClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": _API_VERSION,
                "User-Agent": "peearh-review-bot",
            },
            timeout=30.0,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        last_error: GitHubError | None = None
        for attempt in range(3):
            response = await self._client.request(method, url, **kwargs)
            if response.status_code in {502, 503, 504} and attempt < 2:
                last_error = GitHubError(
                    response.status_code,
                    response.reason_phrase,
                    response.text,
                )
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            if response.status_code >= 400:
                raise GitHubError(
                    response.status_code,
                    response.reason_phrase,
                    response.text,
                )
            return response
        assert last_error is not None
        raise last_error

    async def get_repo(self, owner: str, repo: str) -> RepoInfo:
        response = await self._request("GET", f"/repos/{owner}/{repo}")
        data = response.json()
        return RepoInfo(
            full_name=data["full_name"],
            description=data.get("description"),
            html_url=data.get("html_url", ""),
            default_branch=data.get("default_branch", ""),
            language=data.get("language"),
        )

    async def get_pull(self, owner: str, repo: str, number: int) -> PullRequest:
        response = await self._request(
            "GET", f"/repos/{owner}/{repo}/pulls/{number}"
        )
        return GitHubPullPayload.model_validate(response.json()).to_pull()

    async def list_pull_files(
        self, owner: str, repo: str, number: int
    ) -> list[PullFile]:
        files: list[PullFile] = []
        page = 1
        while True:
            response = await self._request(
                "GET",
                f"/repos/{owner}/{repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            batch = response.json()
            if not batch:
                break
            for item in batch:
                files.append(
                    PullFile(
                        filename=item["filename"],
                        status=item.get("status", "modified"),
                        patch=item.get("patch"),
                        previous_filename=item.get("previous_filename"),
                        additions=item.get("additions", 0),
                        deletions=item.get("deletions", 0),
                        changes=item.get("changes", 0),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return files

    async def create_review(
        self,
        owner: str,
        repo: str,
        number: int,
        *,
        commit_id: str,
        body: str,
        comments: list[ReviewComment],
        event: str = "COMMENT",
    ) -> CreatedReview:
        payload: dict[str, Any] = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
            "comments": [
                {
                    "path": comment.path,
                    "line": comment.line,
                    "side": comment.side,
                    "body": comment.body,
                }
                for comment in comments
            ],
        }
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            json=payload,
        )
        data = response.json()
        return CreatedReview(
            id=data["id"],
            html_url=data.get("html_url", ""),
            state=data.get("state", ""),
        )

    async def create_issue_comment(
        self, owner: str, repo: str, number: int, body: str
    ) -> int:
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            json={"body": body},
        )
        return int(response.json()["id"])
