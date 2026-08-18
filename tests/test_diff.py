from app.github_api.diff import parse_patch


def test_added_file_lines_are_right_side() -> None:
    patch = "@@ -0,0 +1,3 @@\n+alpha\n+beta\n+gamma\n"
    lines = parse_patch("new.txt", patch)
    assert [(item.line, item.side) for item in lines] == [
        (1, "RIGHT"),
        (2, "RIGHT"),
        (3, "RIGHT"),
    ]


def test_deleted_file_lines_are_left_side() -> None:
    patch = "@@ -1,3 +0,0 @@\n-alpha\n-beta\n-gamma\n"
    lines = parse_patch("gone.txt", patch)
    assert [(item.line, item.side) for item in lines] == [
        (1, "LEFT"),
        (2, "LEFT"),
        (3, "LEFT"),
    ]


def test_mixed_hunk_maps_context_plus_and_minus() -> None:
    patch = """@@ -10,4 +10,5 @@ def login(user):
     password = user.password
     if not password:
         raise ValueError("missing")
+    print(password)
     return authenticate(user)
"""
    lines = parse_patch("src/login.py", patch)
    rights = [item.line for item in lines if item.side == "RIGHT"]
    lefts = [item.line for item in lines if item.side == "LEFT"]
    assert rights == [10, 11, 12, 13, 14]
    assert lefts == [10, 11, 12, 13]


def test_empty_or_missing_patch() -> None:
    assert parse_patch("a.bin", None) == []
    assert parse_patch("a.bin", "") == []


def test_no_newline_marker_is_ignored() -> None:
    patch = "@@ -1,1 +1,1 @@\n-old\n+new\n\\ No newline at end of file\n"
    lines = parse_patch("a.txt", patch)
    assert [(item.line, item.side) for item in lines] == [
        (1, "LEFT"),
        (1, "RIGHT"),
    ]
