from __future__ import annotations

from app.jobs import JobStatus
from tests.conftest import pr_payload, signed_request


def test_invalid_signature_is_rejected(client) -> None:
    response = signed_request(
        client, pr_payload(), secret="wrong-secret"
    )
    assert response.status_code == 401


def test_missing_signature_is_rejected(client) -> None:
    response = client.post(
        "/webhooks/github",
        json=pr_payload(),
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert response.status_code == 401


def test_ping_returns_pong(client) -> None:
    response = signed_request(client, {"zen": "keep it simple"}, event="ping")
    assert response.status_code == 200
    assert response.json()["status"] == "pong"


def test_opened_non_draft_is_accepted(client, app_bundle) -> None:
    response = signed_request(client, pr_payload(action="opened"))
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == JobStatus.ACCEPTED.value
    assert body["repo"] == "acme/widgets"
    assert body["pr_number"] == 7
    stored = app_bundle["jobs"].get(body["id"])
    assert stored is not None


def test_ready_for_review_is_accepted(client) -> None:
    response = signed_request(
        client, pr_payload(action="ready_for_review"), delivery="d-ready"
    )
    assert response.status_code == 202
    assert response.json()["status"] == JobStatus.ACCEPTED.value


def test_draft_is_ignored(client) -> None:
    response = signed_request(
        client, pr_payload(draft=True), delivery="d-draft"
    )
    assert response.status_code == 202
    assert response.json()["status"] == JobStatus.IGNORED.value
    assert "draft" in response.json()["reason"]


def test_synchronize_is_accepted(client) -> None:
    response = signed_request(
        client, pr_payload(action="synchronize", sha="newsha99"), delivery="d-sync"
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == JobStatus.ACCEPTED.value
    assert body["action"] == "synchronize"
    assert body["head_sha"] == "newsha99"


def test_synchronize_same_sha_is_duplicate(client) -> None:
    first = signed_request(client, pr_payload(action="opened"), delivery="d-open")
    assert first.json()["status"] == JobStatus.ACCEPTED.value
    second = signed_request(
        client, pr_payload(action="synchronize"), delivery="d-sync-same"
    )
    assert second.status_code == 202
    assert second.json()["status"] == JobStatus.DUPLICATE.value


def test_draft_synchronize_is_ignored(client) -> None:
    response = signed_request(
        client,
        pr_payload(action="synchronize", draft=True, sha="draftsha"),
        delivery="d-sync-draft",
    )
    assert response.status_code == 202
    assert response.json()["status"] == JobStatus.IGNORED.value
    assert "draft" in response.json()["reason"]


def test_unregistered_repo_is_ignored(client) -> None:
    response = signed_request(
        client,
        pr_payload(repo="other/unknown"),
        delivery="d-unknown",
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == JobStatus.IGNORED.value
    assert "no agent" in body["reason"]


def test_second_registered_repo_is_accepted(client, github) -> None:
    created = client.post(
        "/repos",
        json={
            "repo": "acme/storefront",
            "name": "Storefront",
            "description": "Customer UI",
        },
    )
    assert created.status_code == 201
    github.add_pull(
        "acme/storefront",
        3,
        title="Button",
        sha="fff111",
        filename="ui/button.tsx",
        patch="@@ -1,1 +1,1 @@\n-a\n+b\n",
    )
    response = signed_request(
        client,
        pr_payload(repo="acme/storefront", number=3, sha="fff111"),
        delivery="d-storefront",
    )
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["repo"] == "acme/storefront"


def test_duplicate_delivery_is_detected(client) -> None:
    first = signed_request(client, pr_payload(), delivery="same-id")
    second = signed_request(client, pr_payload(), delivery="same-id")
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["status"] == "duplicate"
    assert second.json()["job_id"] == first.json()["id"]
