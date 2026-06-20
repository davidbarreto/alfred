from __future__ import annotations

import logging

from google import genai
from google.genai import types

from app.shared.llm import LlmResponse

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

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> LlmResponse:
        logger.debug("GoogleLLM: calling model=%s messages=%d", self._model_name, len(messages))

        # Merge consecutive same-role messages — Gemini requires strict
        # user/model alternation; two back-to-back user turns cause it to
        # ignore the system prompt and fall back to its default identity.
        sanitized: list[dict[str, str]] = []
        for msg in messages:
            if sanitized and sanitized[-1]["role"] == msg["role"]:
                sanitized[-1] = {
                    "role": msg["role"],
                    "content": sanitized[-1]["content"] + "\n" + msg["content"],
                }
            else:
                sanitized.append(msg)

        contents = [
            types.Content(
                role="model" if msg["role"] == "assistant" else "user",
                parts=[types.Part(text=msg["content"])],
            )
            for msg in sanitized
        ]

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
        return LlmResponse(
            text=response.text or "",
            tokens_input=usage.prompt_token_count if usage else None,
            tokens_output=usage.candidates_token_count if usage else None,
        )
