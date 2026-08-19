from app.github_api.diff import parse_patch
from app.github_api.models import PullFile, PullRequest
from app.review.prompts import file_user_prompt
from tests.conftest import SAMPLE_PATCH


def test_file_prompt_is_title_and_patch_only() -> None:
    body = "please review this leftover debug print " + ("A" * 4000)
    pull = PullRequest(
        number=7,
        title="Log passwords",
        body=body,
        head_sha="abc",
        user_login="dev",
    )
    file = PullFile(filename="src/login.py", status="modified", patch=SAMPLE_PATCH)
    text = file_user_prompt(pull, file, parse_patch(file.filename, file.patch))
    assert "PR #7: Log passwords" in text
    assert "src/login.py" in text
    assert SAMPLE_PATCH.strip() in text
    assert body not in text
    assert "AAA" not in text
    assert "You are reviewing this PR as" not in text
    assert "Author:" not in text
    assert "Description:" not in text
