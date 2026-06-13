from __future__ import annotations

from openai import AsyncOpenAI

_DIMENSIONS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingProvider:
    """Implements EmbeddingProvider backed by the OpenAI embeddings API."""

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def embed(self, text: str) -> list[float]:
        response = await self._client.embeddings.create(input=text, model=self._model)
        return response.data[0].embedding

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return _DIMENSIONS.get(self._model, 1536)
