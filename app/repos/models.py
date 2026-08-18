from __future__ import annotations

import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class RepoRecord(BaseModel):
    repo: str
    name: str = ""
    description: str = ""
    review_focus: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        value = value.strip()
        if not _REPO_RE.match(value):
            raise ValueError("repo must be in owner/name format")
        return value

    @property
    def owner(self) -> str:
        return self.repo.split("/", 1)[0]

    @property
    def name_only(self) -> str:
        return self.repo.split("/", 1)[1]

    @property
    def display_name(self) -> str:
        return self.name or self.name_only

    def brief(self) -> str:
        parts = [f"Repository: {self.repo}"]
        if self.display_name and self.display_name != self.repo:
            parts.append(f"Agent name: {self.display_name}")
        if self.description:
            parts.append(f"About: {self.description}")
        if self.review_focus:
            parts.append(f"Review focus: {self.review_focus}")
        return "\n".join(parts)


class RepoCreate(BaseModel):
    repo: str
    name: str = ""
    description: str = ""
    review_focus: str = ""

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        value = value.strip()
        if not _REPO_RE.match(value):
            raise ValueError("repo must be in owner/name format")
        return value
