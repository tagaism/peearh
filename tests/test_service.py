from __future__ import annotations

import json

import pytest

from app.github_api.models import PullFile
from app.jobs import JobStatus, JobStore
from app.review.agent import ReviewAgent
from app.review.schema import InlineComment
from tests.conftest import SAMPLE_PATCH
from tests.fakes import FakeGitHub, FakeLLM


@pytest.fixture
def agent(app_bundle) -> ReviewAgent:
    found = app_bundle["registry"].get("acme/widgets")
    assert found is not None
    return found


async def test_valid_comment_is_posted_invalid_is_summarized(
    agent: ReviewAgent, github: FakeGitHub, llm: FakeLLM
) -> None:
    llm._text = json.dumps(
        {
            "summary": "Password leaked to stdout.",
            "comments": [
                {
                    "path": "src/login.py",
                    "line": 13,
                    "side": "RIGHT",
                    "severity": "security",
                    "body": "Do not print passwords.",
                },
                {
                    "path": "src/login.py",
                    "line": 99,
                    "side": "RIGHT",
                    "severity": "bug",
                    "body": "This line is not in the diff.",
                },
            ],
        }
    )
    jobs: JobStore = agent.jobs
    job = jobs.create(repo="acme/widgets", pr_number=7, head_sha="abc123def")
    result = await agent.review_pr(job)
    assert result.status == JobStatus.DONE
    assert len(github.reviews) == 1
    review = github.reviews[0]
    assert review["event"] == "COMMENT"
    assert review["commit_id"] == "abc123def"
    assert len(review["comments"]) == 1
    comment = review["comments"][0]
    assert comment.path == "src/login.py"
    assert comment.line == 13
    assert comment.side == "RIGHT"
    assert "password" in comment.body.lower()
    assert "Could not attach" in review["body"]
    assert "not in the diff" in review["body"]
    assert "Widgets" in review["body"]
    kinds = [event.kind for event in result.events]
    assert "reasoning" in kinds
    assert "fetch" in kinds
    assert "done" in kinds


async def test_junk_files_are_skipped_and_not_sent_to_llm(
    agent: ReviewAgent, github: FakeGitHub, llm: FakeLLM
) -> None:
    github.files[("acme/widgets", 7)] = [
        PullFile(
            filename="package-lock.json",
            status="modified",
            patch="@@ -1,1 +1,1 @@\n-a\n+b\n",
        ),
        PullFile(
            filename="frontend/dist/bundle.js",
            status="modified",
            patch="@@ -1,1 +1,1 @@\n-a\n+b\n",
        ),
        PullFile(
            filename="src/login.py",
            status="modified",
            patch=SAMPLE_PATCH,
        ),
    ]
    job = agent.jobs.create(repo="acme/widgets", pr_number=7, head_sha="abc123def")
    result = await agent.review_pr(job)
    assert result.status == JobStatus.DONE
    assert len(llm.complete_calls) == 1
    user = llm.complete_calls[0][1]["content"]
    assert "src/login.py" in user
    assert "package-lock.json" not in user
    assert "bundle.js" not in user
    body = github.reviews[0]["body"]
    assert "package-lock.json" in body
    assert "frontend/dist/bundle.js" in body


async def test_review_prompt_omits_pr_body(
    agent: ReviewAgent, github: FakeGitHub, llm: FakeLLM
) -> None:
    github.pulls[("acme/widgets", 7)].body = "SECRET_PR_BODY_SHOULD_NOT_BE_SENT"
    job = agent.jobs.create(repo="acme/widgets", pr_number=7, head_sha="abc123def")
    await agent.review_pr(job)
    user = llm.complete_calls[0][1]["content"]
    assert "SECRET_PR_BODY_SHOULD_NOT_BE_SENT" not in user
    assert "Log passwords" in user


async def test_failure_posts_issue_comment(
    agent: ReviewAgent, github: FakeGitHub
) -> None:
    github.fail_review_with = RuntimeError("boom")
    jobs: JobStore = agent.jobs
    job = jobs.create(repo="acme/widgets", pr_number=7, head_sha="abc123def")
    result = await agent.review_pr(job)
    assert result.status == JobStatus.FAILED
    assert github.issue_comments
    assert "failed" in github.issue_comments[0]["body"].lower()


async def test_each_repo_gets_its_own_agent(app_bundle, github: FakeGitHub) -> None:
    registry = app_bundle["registry"]
    registry.register(
        repo="acme/storefront",
        name="Storefront",
        description="Customer-facing UI.",
        review_focus="accessibility",
    )
    github.add_pull(
        "acme/storefront",
        3,
        title="Button color",
        sha="fff",
        filename="ui/button.tsx",
        patch=SAMPLE_PATCH.replace("login", "button"),
    )
    widgets = registry.get("acme/widgets")
    storefront = registry.get("acme/storefront")
    assert widgets is not None and storefront is not None
    assert widgets is not storefront
    assert widgets.record.display_name == "Widgets"
    assert storefront.record.review_focus == "accessibility"
    assert {r.repo for r in registry.list_records()} == {
        "acme/widgets",
        "acme/storefront",
    }


def test_filter_uses_diff_index(agent: ReviewAgent) -> None:
    allowed = {("src/login.py", 13, "RIGHT")}
    reviews = [
        (
            github_file(),
            type("R", (), {"comments": [
                InlineComment(
                    path="src/login.py",
                    line=13,
                    side="RIGHT",
                    severity="security",
                    body="ok",
                ),
                InlineComment(
                    path="src/login.py",
                    line=1,
                    side="RIGHT",
                    severity="nit",
                    body="nope",
                ),
            ]})(),
        )
    ]
    attached, leftover = agent._filter_comments(reviews, allowed)  # type: ignore[arg-type]
    assert [c.line for c in attached] == [13]
    assert [c.line for c in leftover] == [1]


def github_file():
    from app.github_api.models import PullFile

    return PullFile(filename="src/login.py", status="modified", patch="x")
