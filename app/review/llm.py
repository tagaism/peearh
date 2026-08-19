from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import Settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


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

    async def complete(self, messages: list[dict[str, str]]) -> str:
        model = await self.model_id()
        try:
            response = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=self._settings.llm_max_tokens,
            )
        except Exception as exc:
            raise LLMError(f"LLM completion failed: {exc}") from exc
        choice = response.choices[0].message.content if response.choices else None
        if not choice:
            raise LLMError("LLM returned an empty completion")
        return choice
