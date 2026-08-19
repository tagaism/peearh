from app.review.skip import skip_reason


def test_lockfiles_are_skipped() -> None:
    assert skip_reason("package-lock.json")
    assert skip_reason("frontend/yarn.lock")
    assert skip_reason("go.sum")


def test_minified_and_maps_are_skipped() -> None:
    assert skip_reason("static/app.min.js")
    assert skip_reason("static/app.js.map")
    assert skip_reason("theme.min.css")


def test_images_and_binaries_are_skipped() -> None:
    assert skip_reason("assets/logo.png")
    assert skip_reason("docs/diagram.svg")
    assert skip_reason("vendor.bin.wasm")


def test_generated_directories_are_skipped() -> None:
    assert skip_reason("frontend/dist/bundle.js")
    assert skip_reason("node_modules/left-pad/index.js")
    assert skip_reason("app/__pycache__/main.py")


def test_source_files_are_reviewed() -> None:
    assert skip_reason("app/review/agent.py") is None
    assert skip_reason("frontend/src/App.tsx") is None
    assert skip_reason("app/build.py") is None
    assert skip_reason("package.json") is None
