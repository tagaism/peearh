from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings

logger = logging.getLogger(__name__)

_AFFORD_RE = re.compile(r"can only afford (\d+)", re.IGNORECASE)


class LLMError(Exception):
    pass


@dataclass
class Completion:
    content: str
    reasoning: str = ""


def _is_unsupported_json_mode(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return False
    if isinstance(status, int) and status not in {400, 422}:
        return False
    text = str(exc).lower()
    return (
        "response_format" in text
        or "json_object" in text
        or "json mode" in text
    )


def _is_credit_limit(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status == 402:
        return True
    return "can only afford" in text or (
        "402" in text and ("credit" in text or "max_tokens" in text)
    )


def _affordable_tokens(exc: Exception) -> int | None:
    match = _AFFORD_RE.search(str(exc))
    if not match:
        return None
    return int(match.group(1))


class LLMClient:
    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or AsyncOpenAI(
            base_url=settings.llm_base_url.rstrip("/"),
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            default_headers={
                "HTTP-Referer": "https://github.com/tagaism/peearh",
                "X-Title": "Peearh",
            },
        )
        self._resolved_model: str | None = settings.llm_model or None
        self._json_mode = True
        self._include_reasoning = True
        self._max_tokens = settings.llm_max_tokens

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.close()

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
        except Exception as exc:
            raise LLMError(f"LLM is unreachable at {self._settings.llm_base_url}: {exc}") from exc
        return [item.id for item in page.data]

    async def model_id(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        models = await self.list_models()
        if not models:
            raise LLMError(f"No models available at {self._settings.llm_base_url}")
        self._resolved_model = models[0]
        logger.info("Using model %s", self._resolved_model)
        return self._resolved_model

    async def complete(self, messages: list[dict[str, str]]) -> Completion:
        model = await self.model_id()
        last_exc: Exception | None = None
        for _ in range(4):
            try:
                return await self._complete_once(
                    model,
                    messages,
                    json_mode=self._json_mode,
                    max_tokens=self._max_tokens,
                    include_reasoning=self._include_reasoning,
                )
            except Exception as exc:
                last_exc = exc
                if self._json_mode and _is_unsupported_json_mode(exc):
                    logger.warning(
                        "LLM rejected json_object response_format; retrying without it"
                    )
                    self._json_mode = False
                    continue
                if _is_credit_limit(exc):
                    afford = _affordable_tokens(exc)
                    if afford is not None and afford < self._max_tokens:
                        new_cap = max(64, afford)
                        logger.warning(
                            "LLM 402: lowering max_tokens %s -> %s",
                            self._max_tokens,
                            new_cap,
                        )
                        self._max_tokens = new_cap
                        self._include_reasoning = False
                        continue
                    raise LLMError(
                        "LLM completion failed: OpenRouter 402 — remaining "
                        "credits (or this key's monthly limit) cannot cover "
                        f"max_tokens={self._max_tokens}. Lower LLM_MAX_TOKENS, "
                        f"raise the key limit, or add credits. Original: {exc}"
                    ) from exc
                raise LLMError(f"LLM completion failed: {exc}") from exc
        raise LLMError(f"LLM completion failed: {last_exc}") from last_exc

    async def _complete_once(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        json_mode: bool,
        max_tokens: int,
        include_reasoning: bool,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        extra: dict[str, Any] = {}
        if include_reasoning:
            extra["include_reasoning"] = True
        if extra:
            kwargs["extra_body"] = extra
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self._client.chat.completions.create(**kwargs)
        if not response.choices:
            raise LLMError("LLM returned an empty completion")
        message = response.choices[0].message
        content = message.content or ""
        if not content:
            raise LLMError("LLM returned an empty completion")
        return Completion(content=content, reasoning=_message_reasoning(message))


def _message_reasoning(message: Any) -> str:
    for attr in ("reasoning", "reasoning_content"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    extra = getattr(message, "model_extra", None) or {}
    if isinstance(extra, dict):
        for key in ("reasoning", "reasoning_content"):
            value = extra.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""
