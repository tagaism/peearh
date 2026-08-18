from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml

from app.repos.models import RepoRecord


class RepoStore:
    """YAML-backed registry of repositories the bot reviews."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._repos: dict[str, RepoRecord] = {}
        self.load()

    def load(self) -> None:
        self._repos = {}
        if not self.path.exists():
            return
        raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        entries = raw.get("repos", raw) if isinstance(raw, dict) else raw
        if not isinstance(entries, list):
            return
        for item in entries:
            if not isinstance(item, dict):
                continue
            record = RepoRecord.model_validate(item)
            self._repos[record.repo.lower()] = record

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "repos": [record.model_dump(mode="json") for record in self.list()]
        }
        self.path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )

    def list(self) -> list[RepoRecord]:
        return sorted(self._repos.values(), key=lambda r: r.repo.lower())

    def get(self, full_name: str) -> RepoRecord | None:
        return self._repos.get(full_name.lower())

    def upsert(
        self,
        *,
        repo: str,
        name: str = "",
        description: str = "",
        review_focus: str = "",
    ) -> RepoRecord:
        existing = self.get(repo)
        now = datetime.now(timezone.utc)
        if existing:
            data = existing.model_dump()
            if name:
                data["name"] = name
            if description:
                data["description"] = description
            if review_focus:
                data["review_focus"] = review_focus
            data["updated_at"] = now
            record = RepoRecord.model_validate(data)
        else:
            record = RepoRecord(
                repo=repo,
                name=name,
                description=description,
                review_focus=review_focus,
                created_at=now,
                updated_at=now,
            )
        self._repos[record.repo.lower()] = record
        self.save()
        return record

    def add_many(self, records: Iterable[RepoRecord]) -> None:
        for record in records:
            self._repos[record.repo.lower()] = record
