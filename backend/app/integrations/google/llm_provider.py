from __future__ import annotations

import logging
import time

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.shared.llm import LlmResponse

logger = logging.getLogger(__name__)


class GoogleLlmProvider:
    """LlmProvider implementation backed by Google Gemini via pydantic-ai."""

    def __init__(self, api_key: str, model_name: str) -> None:
        self._api_key = api_key
        self._model_name = model_name

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
        google_model = GoogleModel(
            self._model_name,
            provider=GoogleProvider(api_key=self._api_key),
        )
        agent = Agent(google_model, output_type=str, system_prompt=system or "")

        history = []
        for msg in messages[:-1]:
            if msg["role"] == "user":
                history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
            else:
                history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))

        t0 = time.monotonic()
        result = await agent.run(messages[-1]["content"], message_history=history)
        latency_ms = int((time.monotonic() - t0) * 1000)
        usage = result.usage()
        logger.info(
            "GoogleLLM: model=%s latency_ms=%d tokens_in=%s tokens_out=%s",
            self._model_name, latency_ms, usage.request_tokens, usage.response_tokens,
        )
        return LlmResponse(
            text=result.output,
            tokens_input=usage.request_tokens,
            tokens_output=usage.response_tokens,
        )
