from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.repository import EmbeddingRepository
from app.features.core.embeddings.schemas import (
    EmbeddingCreate,
    EmbeddingRead,
    EmbeddingSearchRequest,
    EmbeddingSearchResult,
)
from app.shared.embedding import EmbeddingProvider

logger = logging.getLogger(__name__)


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
        logger.debug("Embedding upserted: source_type=%s source_id=%d model=%s", data.source_type, data.source_id, self._provider.model)
        return EmbeddingRead.model_validate(obj)

    async def search(self, request: EmbeddingSearchRequest) -> list[EmbeddingSearchResult]:
        query_vector = await self._provider.embed(request.query)
        rows = await self._repo.search(
            query_vector=query_vector,
            source_types=request.source_types,
            limit=request.limit,
            threshold=request.threshold,
        )
        results = [
            EmbeddingSearchResult(
                **EmbeddingRead.model_validate(obj).model_dump(),
                similarity=round(similarity, 4),
            )
            for obj, similarity in rows
        ]
        logger.debug("Embedding search: source_types=%s limit=%d threshold=%s results=%d", request.source_types, request.limit, request.threshold, len(results))
        return results

    async def delete(self, embedding_id: int) -> bool:
        deleted = await self._repo.delete(embedding_id)
        if deleted:
            logger.info("Embedding deleted: id=%d", embedding_id)
        return deleted

    async def delete_by_source(self, source_type: str, source_id: int) -> bool:
        existing = await self._repo.get_by_source(source_type, source_id)
        if existing is None:
            return False
        return await self.delete(existing.id)
