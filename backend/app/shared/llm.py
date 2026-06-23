from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncGenerator, Protocol, runtime_checkable


@dataclass
class LlmResponse:
    text: str
    tokens_input: int | None
    tokens_output: int | None
    finish_reason: str | None = None


@dataclass
class StreamMeta:
    """Mutable container passed into stream() so callers can read finish_reason after iteration."""
    finish_reason: str | None = None
    truncated: bool = field(default=False, init=False)

    def set_finish_reason(self, reason: str | None) -> None:
        self.finish_reason = reason
        self.truncated = bool(reason and reason != "STOP")


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

    def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        meta: StreamMeta | None = None,
    ) -> AsyncGenerator[str, None]: ...
