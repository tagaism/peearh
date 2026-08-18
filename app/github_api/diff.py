from __future__ import annotations

import re
from dataclasses import dataclass

_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


@dataclass(frozen=True)
class CommentableLine:
    path: str
    line: int
    side: str  # LEFT or RIGHT


def parse_patch(path: str, patch: str | None) -> list[CommentableLine]:
    """Map a GitHub file patch to (path, line, side) pairs GitHub will accept."""
    if not patch:
        return []

    lines: list[CommentableLine] = []
    old_line = 0
    new_line = 0
    in_hunk = False

    for raw in patch.splitlines():
        header = _HUNK_RE.match(raw)
        if header:
            old_line = int(header.group(1))
            new_line = int(header.group(3))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith("\\"):
            continue
        if raw.startswith("+"):
            lines.append(CommentableLine(path=path, line=new_line, side="RIGHT"))
            new_line += 1
        elif raw.startswith("-"):
            lines.append(CommentableLine(path=path, line=old_line, side="LEFT"))
            old_line += 1
        elif raw.startswith(" "):
            lines.append(CommentableLine(path=path, line=new_line, side="RIGHT"))
            lines.append(CommentableLine(path=path, line=old_line, side="LEFT"))
            old_line += 1
            new_line += 1
        else:
            # Unexpected line (file headers inside a patch). Reset hunk.
            in_hunk = False

    return lines


def commentable_index(
    path: str, patch: str | None
) -> set[tuple[str, int, str]]:
    return {(item.path, item.line, item.side) for item in parse_patch(path, patch)}
