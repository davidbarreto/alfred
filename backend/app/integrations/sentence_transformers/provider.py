from __future__ import annotations

import asyncio
from functools import cached_property

from sentence_transformers import SentenceTransformer


class SentenceTransformerEmbeddingProvider:
    """Implements EmbeddingProvider using a local sentence-transformers model.

    The model is loaded once on first access and reused across requests.
    Inference runs in a thread-pool executor to avoid blocking the event loop.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name

    @cached_property
    def _model(self) -> SentenceTransformer:
        return SentenceTransformer(self._model_name)

    async def embed(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        vector = await loop.run_in_executor(
            None, lambda: self._model.encode(text, convert_to_numpy=True).tolist()
        )
        return vector

    @property
    def model(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._model.get_sentence_embedding_dimension()
