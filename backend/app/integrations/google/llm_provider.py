from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.shared.llm import LlmResponse


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

        result = await agent.run(messages[-1]["content"], message_history=history)
        usage = result.usage()
        return LlmResponse(
            text=result.output,
            tokens_input=usage.request_tokens,
            tokens_output=usage.response_tokens,
        )
