from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app
from app.jobs import JobStore
from app.repos.store import RepoStore
from tests.conftest import SECRET, pr_payload, signed_request
from tests.fakes import FakeGitHub, FakeLLM


def test_allow_unregistered_creates_agent_from_github_brief(tmp_path: Path) -> None:
    repos_file = tmp_path / "repos.yaml"
    repos_file.write_text("repos: []\n", encoding="utf-8")
    settings = Settings(
        github_webhook_secret=SECRET,
        github_token="test-token",
        llm_model="fake-model",
        repos_file=repos_file,
        allow_unregistered=True,
    )
    github = FakeGitHub()
    github.add_repo(
        "acme/new-service",
        description="Brand new service",
        language="Go",
    )
    github.add_pull(
        "acme/new-service",
        1,
        title="Init",
        sha="aaa",
        filename="main.go",
        patch="@@ -0,0 +1,1 @@\n+package main\n",
    )
    app = create_app(
        settings,
        github=github,
        llm=FakeLLM(),
        repo_store=RepoStore(repos_file),
        jobs=JobStore(),
    )
    with TestClient(app) as client:
        response = signed_request(
            client,
            pr_payload(repo="acme/new-service", number=1, sha="aaa"),
            delivery="d-new",
        )
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"
        listed = client.get("/repos").json()["repos"]
        assert any(item["repo"] == "acme/new-service" for item in listed)
        brief = client.get("/repos/acme/new-service").json()
        assert "Brand new service" in brief["description"]
        assert "Go" in brief["description"]
