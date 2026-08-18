from __future__ import annotations

from pydantic import BaseModel, Field


class PullRequest(BaseModel):
    number: int
    title: str = ""
    body: str | None = None
    draft: bool = False
    html_url: str = ""
    head_sha: str
    head_ref: str = ""
    user_login: str = ""


class PullFile(BaseModel):
    filename: str
    status: str
    patch: str | None = None
    previous_filename: str | None = None
    additions: int = 0
    deletions: int = 0
    changes: int = 0


class RepoInfo(BaseModel):
    full_name: str
    description: str | None = None
    html_url: str = ""
    default_branch: str = ""
    language: str | None = None


class ReviewComment(BaseModel):
    path: str
    line: int
    side: str = "RIGHT"
    body: str


class CreatedReview(BaseModel):
    id: int
    html_url: str = ""
    state: str = ""


class GitHubUser(BaseModel):
    login: str = ""


class GitHubRef(BaseModel):
    sha: str = ""
    ref: str = ""


class GitHubPullPayload(BaseModel):
    number: int
    title: str = ""
    body: str | None = None
    draft: bool = False
    html_url: str = ""
    user: GitHubUser = Field(default_factory=GitHubUser)
    head: GitHubRef = Field(default_factory=GitHubRef)

    def to_pull(self) -> PullRequest:
        return PullRequest(
            number=self.number,
            title=self.title,
            body=self.body,
            draft=self.draft,
            html_url=self.html_url,
            head_sha=self.head.sha,
            head_ref=self.head.ref,
            user_login=self.user.login,
        )
