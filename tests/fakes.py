from __future__ import annotations

from app.github_api.models import (
    CreatedReview,
    PullFile,
    PullRequest,
    RepoInfo,
    ReviewComment,
)
from app.review.llm import Completion


class FakeGitHub:
    def __init__(self) -> None:
        self.pulls: dict[tuple[str, int], PullRequest] = {}
        self.files: dict[tuple[str, int], list[PullFile]] = {}
        self.repos: dict[str, RepoInfo] = {}
        self.reviews: list[dict] = []
        self.issue_comments: list[dict] = []
        self.fail_review_with: Exception | None = None

    async def aclose(self) -> None:
        return None

    def add_repo(
        self, full_name: str, *, description: str = "", language: str = "Python"
    ) -> None:
        self.repos[full_name.lower()] = RepoInfo(
            full_name=full_name,
            description=description,
            html_url=f"https://github.com/{full_name}",
            default_branch="main",
            language=language,
        )

    def add_pull(
        self,
        repo: str,
        number: int,
        *,
        title: str,
        sha: str,
        filename: str,
        patch: str,
        draft: bool = False,
    ) -> None:
        owner, name = repo.split("/", 1)
        key = (repo.lower(), number)
        self.pulls[key] = PullRequest(
            number=number,
            title=title,
            body="please review",
            draft=draft,
            html_url=f"https://github.com/{owner}/{name}/pull/{number}",
            head_sha=sha,
            head_ref="feat",
            user_login="dev",
        )
        self.files[key] = [
            PullFile(
                filename=filename,
                status="modified",
                patch=patch,
                additions=1,
                deletions=0,
                changes=1,
            )
        ]

    async def get_repo(self, owner: str, repo: str) -> RepoInfo:
        info = self.repos.get(f"{owner}/{repo}".lower())
        if info is None:
            raise RuntimeError(f"unknown repo {owner}/{repo}")
        return info

    async def get_pull(self, owner: str, repo: str, number: int) -> PullRequest:
        return self.pulls[(f"{owner}/{repo}".lower(), number)]

    async def list_pull_files(
        self, owner: str, repo: str, number: int
    ) -> list[PullFile]:
        return list(self.files[(f"{owner}/{repo}".lower(), number)])

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
        if self.fail_review_with:
            raise self.fail_review_with
        payload = {
            "owner": owner,
            "repo": repo,
            "number": number,
            "commit_id": commit_id,
            "body": body,
            "comments": comments,
            "event": event,
        }
        self.reviews.append(payload)
        return CreatedReview(
            id=len(self.reviews),
            html_url=f"https://github.com/{owner}/{repo}/pull/{number}#review",
            state="COMMENTED",
        )

    async def create_issue_comment(
        self, owner: str, repo: str, number: int, body: str
    ) -> int:
        self.issue_comments.append(
            {"owner": owner, "repo": repo, "number": number, "body": body}
        )
        return len(self.issue_comments)


class FakeLLM:
    def __init__(self, replies: list[str] | None = None, text: str | None = None) -> None:
        self.complete_calls: list[list[dict[str, str]]] = []
        self._replies = list(replies or [])
        self._text = text

    async def aclose(self) -> None:
        return None

    async def list_models(self) -> list[str]:
        return ["fake-model"]

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        self.complete_calls.append(messages)
        if self._replies:
            text = self._replies.pop(0)
        elif self._text is not None:
            text = self._text
        else:
            text = '{"summary": "Looks fine.", "comments": []}'
        return Completion(content=text, reasoning="")
