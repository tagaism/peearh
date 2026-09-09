from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import Settings
from app.review.llm import LLMClient, LLMError


class FakeCompletions:
    def __init__(
        self,
        *,
        fail_json: bool = False,
        fail_always: bool = False,
        afford: int | None = None,
    ) -> None:
        self.calls: list[dict] = []
        self.fail_json = fail_json
        self.fail_always = fail_always
        self.afford = afford

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_always:
            raise RuntimeError("provider down")
        if self.fail_json and kwargs.get("response_format"):
            raise RuntimeError("response_format json_object is not supported")
        max_tokens = int(kwargs.get("max_tokens") or 0)
        if self.afford is not None and max_tokens > self.afford:
            err = RuntimeError(
                "Error code: 402 - {'error': {'message': "
                f"\"You requested up to {max_tokens} tokens, but can only "
                f"afford {self.afford}.\"}}"
            )
            err.status_code = 402  # type: ignore[attr-defined]
            raise err
        message = SimpleNamespace(
            content='{"summary": "ok", "comments": []}',
            reasoning="Checking the diff for bugs.",
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _client(tmp_path, completions: FakeCompletions) -> LLMClient:
    settings = Settings(
        github_webhook_secret="s",
        github_token="t",
        llm_model="qwen/qwen3-coder",
        llm_max_tokens=128,
        repos_file=tmp_path / "repos.yaml",
    )
    openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=completions),
        close=lambda: None,
    )
    return LLMClient(settings, client=openai_client)  # type: ignore[arg-type]


async def test_complete_requests_json_object(tmp_path) -> None:
    completions = FakeCompletions()
    llm = _client(tmp_path, completions)
    result = await llm.complete([{"role": "user", "content": "review"}])
    assert "ok" in result.content
    assert result.reasoning == "Checking the diff for bugs."
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["max_tokens"] == 128
    assert completions.calls[0]["extra_body"] == {"include_reasoning": True}


async def test_retries_without_json_mode_when_unsupported(tmp_path) -> None:
    completions = FakeCompletions(fail_json=True)
    llm = _client(tmp_path, completions)
    result = await llm.complete([{"role": "user", "content": "review"}])
    assert "ok" in result.content
    assert len(completions.calls) == 2
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in completions.calls[1]
    await llm.complete([{"role": "user", "content": "again"}])
    assert len(completions.calls) == 3
    assert "response_format" not in completions.calls[2]


async def test_other_errors_are_not_retried(tmp_path) -> None:
    completions = FakeCompletions(fail_always=True)
    llm = _client(tmp_path, completions)
    with pytest.raises(LLMError, match="provider down"):
        await llm.complete([{"role": "user", "content": "review"}])
    assert len(completions.calls) == 1


async def test_402_retries_with_affordable_max_tokens(tmp_path) -> None:
    completions = FakeCompletions(afford=307)
    llm = _client(tmp_path, completions)
    llm._max_tokens = 4096
    result = await llm.complete([{"role": "user", "content": "review"}])
    assert "ok" in result.content
    assert completions.calls[0]["max_tokens"] == 4096
    assert completions.calls[1]["max_tokens"] == 307
    assert "extra_body" not in completions.calls[1]
    again = await llm.complete([{"role": "user", "content": "again"}])
    assert "ok" in again.content
    assert completions.calls[2]["max_tokens"] == 307
