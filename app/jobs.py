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
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

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
        return job

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
