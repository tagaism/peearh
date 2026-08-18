from pathlib import Path

from app.repos.store import RepoStore


def test_upsert_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "repos.yaml"
    store = RepoStore(path)
    store.upsert(
        repo="acme/widgets",
        name="Widgets",
        description="Inventory API",
        review_focus="security",
    )
    store.upsert(
        repo="acme/storefront",
        name="Storefront",
        description="Customer UI",
    )

    reloaded = RepoStore(path)
    names = [record.repo for record in reloaded.list()]
    assert names == ["acme/storefront", "acme/widgets"]
    widgets = reloaded.get("ACME/Widgets")
    assert widgets is not None
    assert widgets.description == "Inventory API"
    assert widgets.review_focus == "security"


def test_upsert_updates_existing_brief(tmp_path: Path) -> None:
    path = tmp_path / "repos.yaml"
    store = RepoStore(path)
    store.upsert(repo="acme/widgets", description="old")
    store.upsert(repo="acme/widgets", description="new", name="Widgets")
    record = store.get("acme/widgets")
    assert record is not None
    assert record.description == "new"
    assert record.name == "Widgets"
    assert len(store.list()) == 1
