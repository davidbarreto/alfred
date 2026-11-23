from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """
    Async interface for generating vector embeddings from text.

    The service layer speaks only this interface, so swapping the
    underlying model (OpenAI, Ollama, …) requires no changes outside
    the integrations layer.
    """

    async def embed(self, text: str) -> list[float]: ...

    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...
