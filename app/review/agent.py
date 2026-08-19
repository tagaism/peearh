from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import Settings
from app.github_api.client import GitHubClient, GitHubError
from app.github_api.diff import CommentableLine, commentable_index, parse_patch
from app.github_api.models import PullFile, PullRequest, ReviewComment
from app.jobs import Job, JobStatus, JobStore
from app.repos.models import RepoRecord
from app.review.llm import LLMClient, LLMError
from app.review.prompts import file_user_prompt, system_prompt
from app.review.schema import FileReview, InlineComment, parse_review_json
from app.review.skip import skip_reason

logger = logging.getLogger(__name__)


@dataclass
class FilePlan:
    file: PullFile
    commentable: list[CommentableLine]
    skip_reason: str | None = None


class ReviewAgent:
    """One review agent bound to a single GitHub repository."""

    def __init__(
        self,
        record: RepoRecord,
        *,
        settings: Settings,
        github: GitHubClient,
        llm: LLMClient,
        jobs: JobStore,
    ) -> None:
        self.record = record
        self.settings = settings
        self.github = github
        self.llm = llm
        self.jobs = jobs

    @property
    def repo(self) -> str:
        return self.record.repo

    async def review_pr(self, job: Job) -> Job:
        if job.pr_number is None:
            return self.jobs.update(
                job,
                status=JobStatus.FAILED,
                error="job is missing pull request number",
            )

        self.jobs.update(job, status=JobStatus.RUNNING)
        owner, name = self.record.owner, self.record.name_only
        number = job.pr_number

        try:
            pull = await self.github.get_pull(owner, name, number)
            files = await self.github.list_pull_files(owner, name, number)
            plans, skipped = self._plan_files(files)
            file_reviews: list[tuple[PullFile, FileReview]] = []
            for plan in plans:
                review = await self._review_file(pull, plan)
                file_reviews.append((plan.file, review))

            allowed = {
                key
                for plan in plans
                for key in commentable_index(plan.file.filename, plan.file.patch)
            }
            attached, leftover = self._filter_comments(file_reviews, allowed)
            body = self._build_summary(pull, file_reviews, leftover, skipped)
            created = await self.github.create_review(
                owner,
                name,
                number,
                commit_id=pull.head_sha,
                body=body,
                comments=[
                    ReviewComment(
                        path=item.path,
                        line=item.line,
                        side=item.side,
                        body=self._format_comment(item),
                    )
                    for item in attached
                ],
            )
            return self.jobs.update(
                job,
                status=JobStatus.DONE,
                head_sha=pull.head_sha,
                result={
                    "review_id": created.id,
                    "html_url": created.html_url,
                    "files_reviewed": [f.filename for f, _ in file_reviews],
                    "files_skipped": [path for path, _ in skipped],
                    "comments_posted": len(attached),
                    "agent": self.record.display_name,
                },
            )
        except (GitHubError, LLMError, Exception) as exc:
            logger.exception(
                "Review failed repo=%s pr=%s job=%s",
                self.record.repo,
                number,
                job.id,
            )
            try:
                await self.github.create_issue_comment(
                    owner,
                    name,
                    number,
                    (
                        f"## Peearh review failed\n\n"
                        f"The **{self.record.display_name}** agent could not "
                        f"finish this review.\n\n`{type(exc).__name__}: {exc}`"
                    ),
                )
            except Exception:
                logger.exception("Also failed to post failure comment")
            return self.jobs.update(job, status=JobStatus.FAILED, error=str(exc))

    def _plan_files(
        self, files: list[PullFile]
    ) -> tuple[list[FilePlan], list[tuple[str, str]]]:
        plans: list[FilePlan] = []
        skipped: list[tuple[str, str]] = []
        remaining_slots = self.settings.max_files
        for file in files:
            junk = skip_reason(file.filename)
            if junk:
                skipped.append((file.filename, junk))
                continue
            if remaining_slots <= 0:
                skipped.append((file.filename, "over MAX_FILES"))
                continue
            if not file.patch:
                skipped.append((file.filename, "no patch (binary or rename)"))
                continue
            if len(file.patch) > self.settings.max_patch_chars:
                skipped.append((file.filename, "patch exceeds MAX_PATCH_CHARS"))
                continue
            commentable = parse_patch(file.filename, file.patch)
            if not commentable:
                skipped.append((file.filename, "no commentable lines"))
                continue
            plans.append(FilePlan(file=file, commentable=commentable))
            remaining_slots -= 1
        return plans, skipped

    async def _review_file(self, pull: PullRequest, plan: FilePlan) -> FileReview:
        messages = [
            {"role": "system", "content": system_prompt(self.record)},
            {
                "role": "user",
                "content": file_user_prompt(pull, plan.file, plan.commentable),
            },
        ]
        raw = await self.llm.complete(messages)
        return parse_review_json(raw, default_path=plan.file.filename)

    def _filter_comments(
        self,
        file_reviews: list[tuple[PullFile, FileReview]],
        allowed: set[tuple[str, int, str]],
    ) -> tuple[list[InlineComment], list[InlineComment]]:
        attached: list[InlineComment] = []
        leftover: list[InlineComment] = []
        seen: set[tuple[str, int, str, str]] = set()
        for _, review in file_reviews:
            for comment in review.comments:
                key = (comment.path, comment.line, comment.side)
                dedupe = (*key, comment.body)
                if dedupe in seen:
                    continue
                seen.add(dedupe)
                if key in allowed:
                    attached.append(comment)
                else:
                    leftover.append(comment)
        return attached, leftover

    def _build_summary(
        self,
        pull: PullRequest,
        file_reviews: list[tuple[PullFile, FileReview]],
        leftover: list[InlineComment],
        skipped: list[tuple[str, str]],
    ) -> str:
        parts = [
            f"## Review by **{self.record.display_name}**",
            "",
            f"Agent for `{self.record.repo}`.",
        ]
        if self.record.description:
            parts.extend(["", self.record.description])
        parts.extend(["", f"PR: **{pull.title}**", ""])

        if file_reviews:
            parts.append("### Files")
            for file, review in file_reviews:
                blurb = review.summary or "Reviewed."
                parts.append(f"- `{file.filename}`: {blurb}")
            parts.append("")

        if leftover:
            parts.append("### Could not attach")
            parts.append(
                "These notes were not on a commentable diff line:"
            )
            for comment in leftover:
                parts.append(
                    f"- `{comment.path}:{comment.line}` "
                    f"({comment.severity}): {comment.body}"
                )
            parts.append("")

        if skipped:
            parts.append("### Skipped")
            for path, reason in skipped:
                parts.append(f"- `{path}` — {reason}")
            parts.append("")

        parts.append("_Posted as `COMMENT` by Peearh. Not an approval._")
        return "\n".join(parts)

    @staticmethod
    def _format_comment(comment: InlineComment) -> str:
        label = comment.severity.upper()
        return f"**{label}** — {comment.body}"
