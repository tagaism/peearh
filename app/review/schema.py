from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["bug", "security", "style", "nit"]
Side = Literal["LEFT", "RIGHT"]

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class InlineComment(BaseModel):
    path: str
    line: int
    side: Side = "RIGHT"
    severity: Severity = "bug"
    body: str

    @field_validator("line")
    @classmethod
    def line_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("line must be >= 1")
        return value

    @field_validator("side", mode="before")
    @classmethod
    def normalize_side(cls, value: object) -> object:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, value: object) -> object:
        if isinstance(value, str):
            lowered = value.lower()
            if lowered not in {"bug", "security", "style", "nit"}:
                return "bug"
            return lowered
        return value

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("body must not be empty")
        return value


class FileReview(BaseModel):
    summary: str = ""
    comments: list[InlineComment] = Field(default_factory=list)


def parse_review_json(text: str, *, default_path: str = "") -> FileReview:
    """Parse model output into a FileReview, degrading to summary-only."""
    candidates = _json_candidates(text)
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        comments: list[InlineComment] = []
        for raw in data.get("comments") or []:
            if not isinstance(raw, dict):
                continue
            payload = dict(raw)
            if not payload.get("path") and default_path:
                payload["path"] = default_path
            try:
                comments.append(InlineComment.model_validate(payload))
            except Exception:
                continue
        summary = str(data.get("summary") or "").strip()
        return FileReview(summary=summary, comments=comments)

    return FileReview(summary=text.strip(), comments=[])


def _json_candidates(text: str) -> list[str]:
    stripped = text.strip()
    candidates = [stripped]
    fenced = _FENCE_RE.search(stripped)
    if fenced:
        candidates.append(fenced.group(1))
    obj = _OBJECT_RE.search(stripped)
    if obj:
        candidates.append(obj.group(0))
    # unique, preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique
