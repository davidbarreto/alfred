from __future__ import annotations

import logging
from typing import AsyncGenerator

from google import genai
from google.genai import types

from app.shared.llm import LlmResponse, StreamMeta

logger = logging.getLogger(__name__)


class GoogleLlmProvider:
    """LlmProvider implementation backed by Google Gemini via google-genai SDK."""

    def __init__(self, api_key: str, model_name: str, temperature: float = 1.0) -> None:
        self._model_name = model_name
        self._temperature = temperature
        self._client = genai.Client(api_key=api_key)

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._model_name

    def _build_contents(
        self,
        messages: list[dict[str, str]],
    ) -> list[types.Content]:
        # Sanitize history to enforce strict user/model alternation that
        # Gemini requires. Consecutive same-role messages are merged. If
        # history ends on a user message, a placeholder bridges the gap.
        history = messages[:-1]
        current = messages[-1]

        sanitized: list[dict[str, str]] = []
        for msg in history:
            if sanitized and sanitized[-1]["role"] == msg["role"]:
                sanitized[-1] = {
                    "role": msg["role"],
                    "content": sanitized[-1]["content"] + "\n" + msg["content"],
                }
            else:
                sanitized.append(msg)

        if sanitized and sanitized[-1]["role"] == "user":
            sanitized.append({"role": "assistant", "content": "(handled)"})

        contents = [
            types.Content(
                role="model" if msg["role"] == "assistant" else "user",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in sanitized
        ]
        contents.append(types.Content(role="user", parts=[types.Part(text=current["content"])]))
        return contents

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> LlmResponse:
        logger.debug("GoogleLLM: calling model=%s messages=%d", self._model_name, len(messages))
        contents = self._build_contents(messages)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=config,
        )

        usage = response.usage_metadata
        finish_reason: str | None = None
        if response.candidates:
            finish_reason = str(response.candidates[0].finish_reason.name)
        return LlmResponse(
            text=response.text or "",
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
            finish_reason=finish_reason,
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        meta: StreamMeta | None = None,
    ) -> AsyncGenerator[str, None]:
        logger.debug("GoogleLLM: streaming model=%s messages=%d", self._model_name, len(messages))
        contents = self._build_contents(messages)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
        )
        finish_reason: str | None = None
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self._model_name,
            contents=contents,
            config=config,
        ):
            if chunk.text:
                yield chunk.text
            if chunk.candidates and chunk.candidates[0].finish_reason:
                finish_reason = chunk.candidates[0].finish_reason.name
        if meta is not None:
            meta.set_finish_reason(finish_reason)
