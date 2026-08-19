from __future__ import annotations

from app.github_api.diff import CommentableLine
from app.github_api.models import PullFile, PullRequest
from app.repos.models import RepoRecord

SYSTEM_PROMPT = """You are {agent_name}, a senior code review agent for {repo}.

{brief}

Review only the provided diff. Focus on correctness, bugs, security issues,
missed edge cases, and broken API contracts. Deprioritize style nits unless
they hide a real bug.

Reply with a single JSON object and nothing else:
{{
  "summary": "1-3 sentences about this file",
  "comments": [
    {{
      "path": "exact/file/path",
      "line": 12,
      "side": "RIGHT",
      "severity": "bug",
      "body": "What is wrong, why it matters, and how to fix it"
    }}
  ]
}}

Rules:
- "side" must be LEFT or RIGHT. Use LEFT only for deleted lines.
- "line" must be one of the commentable lines listed in the user message.
- "severity" must be one of: bug, security, style, nit.
- If the file looks fine, return an empty comments array and a short summary.
- Do not invent files, lines, or issues that are not supported by the diff.
"""


def system_prompt(record: RepoRecord) -> str:
    return SYSTEM_PROMPT.format(
        agent_name=record.display_name,
        repo=record.repo,
        brief=record.brief(),
    )


def file_user_prompt(
    pull: PullRequest,
    file: PullFile,
    commentable: list[CommentableLine],
) -> str:
    allowed = ", ".join(
        f"{item.line}:{item.side}" for item in commentable
    ) or "(none)"
    patch = file.patch or "(no patch)"
    return (
        f"PR #{pull.number}: {pull.title}\n"
        f"File: {file.filename} ({file.status})\n"
        f"Commentable lines (line:side): {allowed}\n\n"
        f"Patch:\n{patch}\n"
    )
