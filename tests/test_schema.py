from app.review.schema import parse_review_json


def test_valid_json() -> None:
    raw = """
    {
      "summary": "Bug in login",
      "comments": [
        {"path": "a.py", "line": 4, "side": "RIGHT", "severity": "security", "body": "leak"}
      ]
    }
    """
    result = parse_review_json(raw)
    assert result.summary == "Bug in login"
    assert len(result.comments) == 1
    assert result.comments[0].severity == "security"
    assert result.comments[0].side == "RIGHT"


def test_fenced_json() -> None:
    raw = """Here you go
```json
{"summary": "ok", "comments": []}
```
"""
    result = parse_review_json(raw)
    assert result.summary == "ok"
    assert result.comments == []


def test_garbage_becomes_summary_only() -> None:
    result = parse_review_json("this is not json at all")
    assert result.summary == "this is not json at all"
    assert result.comments == []


def test_default_path_and_unknown_severity() -> None:
    raw = '{"summary": "x", "comments": [{"line": 2, "severity": "critical", "body": "bad"}]}'
    result = parse_review_json(raw, default_path="src/a.py")
    assert result.comments[0].path == "src/a.py"
    assert result.comments[0].severity == "bug"


def test_invalid_comment_is_dropped() -> None:
    raw = '{"summary": "x", "comments": [{"path": "a.py", "line": 0, "body": "nope"}]}'
    result = parse_review_json(raw)
    assert result.comments == []
