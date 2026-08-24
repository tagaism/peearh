from tests.conftest import pr_payload, signed_request


def test_ui_is_served(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Peearh" in response.text or "peearh" in response.text
    assert "reasoning" in response.text.lower()
    assert "sessions" in response.text
    assert "scrollToNewest" in response.text
    assert "stick" in response.text
    assert "SF Mono" in response.text or "Menlo" in response.text


def test_list_jobs_includes_events(client) -> None:
    accepted = signed_request(client, pr_payload(), delivery="ui-job")
    listed = client.get("/jobs")
    assert listed.status_code == 200
    jobs = listed.json()["jobs"]
    assert any(item["id"] == accepted.json()["id"] for item in jobs)
    match = next(item for item in jobs if item["id"] == accepted.json()["id"])
    assert match["events"]
    assert match["events"][0]["kind"] in {"accepted", "running", "ignored"}


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_llm(client) -> None:
    response = client.get("/health/llm")
    assert response.status_code == 200
    assert response.json()["models"] == ["fake-model"]


def test_list_and_create_repos(client) -> None:
    listed = client.get("/repos")
    assert listed.status_code == 200
    repos = listed.json()["repos"]
    assert any(item["repo"] == "acme/widgets" for item in repos)

    created = client.post(
        "/repos",
        json={
            "repo": "acme/storefront",
            "name": "Storefront",
            "description": "Customer UI",
            "review_focus": "accessibility",
        },
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Storefront"

    fetched = client.get("/repos/acme/storefront")
    assert fetched.status_code == 200
    assert fetched.json()["review_focus"] == "accessibility"


def test_get_unknown_repo(client) -> None:
    response = client.get("/repos/no/such")
    assert response.status_code == 404


def test_get_job_after_webhook(client) -> None:
    accepted = signed_request(client, pr_payload(), delivery="job-lookup")
    job_id = accepted.json()["id"]
    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["repo"] == "acme/widgets"


def test_unknown_job(client) -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404
