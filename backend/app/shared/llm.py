from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LlmResponse:
    text: str
    tokens_input: int | None
    tokens_output: int | None


@runtime_checkable
class LlmProvider(Protocol):
    """
    Async interface for a text-completion LLM.

    The service layer speaks only this interface, so swapping the
    underlying provider (Google, Anthropic, OpenAI, …) requires no
    changes outside the integrations layer.

    messages: OpenAI-style list of {"role": "user"|"assistant", "content": "..."}
    system:   optional system prompt, passed separately so providers that
              handle it natively (Anthropic) can do so correctly
    """

    @property
    def provider(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> LlmResponse: ...
