from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.jobs import JobStore
from app.repos.store import RepoStore
from app.webhooks.signatures import sign_body
from tests.fakes import FakeGitHub, FakeLLM

SECRET = "test-webhook-secret"

SAMPLE_PATCH = """@@ -10,4 +10,5 @@ def login(user):
     password = user.password
     if not password:
         raise ValueError("missing")
+    print(password)
     return authenticate(user)
"""


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    repos_file = tmp_path / "repos.yaml"
    repos_file.write_text("repos: []\n", encoding="utf-8")
    return Settings(
        github_webhook_secret=SECRET,
        github_token="test-token",
        llm_base_url="http://127.0.0.1:1234/v1",
        llm_api_key="lm-studio",
        llm_model="fake-model",
        repos_file=repos_file,
        allow_unregistered=False,
        github_api_base="https://api.github.com",
    )


@pytest.fixture
def github() -> FakeGitHub:
    fake = FakeGitHub()
    fake.add_pull(
        "acme/widgets",
        7,
        title="Log passwords",
        sha="abc123def",
        patch=SAMPLE_PATCH,
        filename="src/login.py",
    )
    fake.add_repo("acme/widgets", description="Inventory widgets API", language="Python")
    return fake


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def app_bundle(settings: Settings, github: FakeGitHub, llm: FakeLLM):
    store = RepoStore(settings.repos_file)
    store.upsert(
        repo="acme/widgets",
        name="Widgets",
        description="Inventory service for widgets.",
        review_focus="security and API contracts",
    )
    jobs = JobStore()
    application = create_app(
        settings,
        github=github,
        llm=llm,
        repo_store=store,
        jobs=jobs,
    )
    return {
        "app": application,
        "settings": settings,
        "github": github,
        "llm": llm,
        "jobs": jobs,
        "store": store,
        "registry": application.state.registry,
    }


@pytest.fixture
def client(app_bundle) -> TestClient:
    with TestClient(app_bundle["app"]) as test_client:
        yield test_client


def signed_request(
    client: TestClient,
    payload: dict,
    *,
    event: str = "pull_request",
    delivery: str = "delivery-1",
    secret: str = SECRET,
):
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        "/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": sign_body(secret=secret, body=body),
        },
    )


def pr_payload(
    *,
    action: str = "opened",
    repo: str = "acme/widgets",
    number: int = 7,
    draft: bool = False,
    sha: str = "abc123def",
) -> dict:
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "number": number,
            "draft": draft,
            "title": "Log passwords",
            "body": "debug leftover",
            "html_url": f"https://github.com/{repo}/pull/{number}",
            "head": {"sha": sha, "ref": "feat/login"},
            "user": {"login": "dev"},
        },
        "repository": {"full_name": repo},
    }
