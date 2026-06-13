from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.repository import EmbeddingRepository
from app.features.core.embeddings.schemas import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingSearchRequest,
    EmbeddingSearchResult,
)
from app.shared.embedding import EmbeddingProvider


class EmbeddingService:
    def __init__(self, session: AsyncSession, provider: EmbeddingProvider) -> None:
        self._repo = EmbeddingRepository(session)
        self._provider = provider

    async def embed(self, data: EmbeddingCreate) -> EmbeddingRead:
        vector = await self._provider.embed(data.content)
        obj = await self._repo.upsert(
            source_type=data.source_type,
            source_id=data.source_id,
            content=data.content,
            vector=vector,
            model=self._provider.model,
            dimensions=self._provider.dimensions,
        )
        return EmbeddingRead.model_validate(obj)

    async def search(self, request: EmbeddingSearchRequest) -> list[EmbeddingSearchResult]:
        query_vector = await self._provider.embed(request.query)
        rows = await self._repo.search(
            query_vector=query_vector,
            source_types=request.source_types,
            limit=request.limit,
            threshold=request.threshold,
        )
        return [
            EmbeddingSearchResult(
                **EmbeddingRead.model_validate(obj).model_dump(),
                similarity=round(similarity, 4),
            )
            for obj, similarity in rows
        ]

    async def delete(self, embedding_id: int) -> bool:
        return await self._repo.delete(embedding_id)
