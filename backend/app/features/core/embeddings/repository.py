from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.tables import Embedding
from app.features.core.memories.tables import Memory


class EmbeddingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, embedding_id: int) -> Embedding | None:
        result = await self._session.execute(
            select(Embedding).where(Embedding.id == embedding_id)
        )
        return result.scalars().first()

    async def get_by_source(self, source_type: str, source_id: int) -> Embedding | None:
        result = await self._session.execute(
            select(Embedding).where(
                Embedding.source_type == source_type,
                Embedding.source_id == source_id,
            )
        )
        return result.scalars().first()

    async def upsert(
        self,
        source_type: str,
        source_id: int,
        content: str,
        vector: list[float],
        model: str,
        dimensions: int,
    ) -> Embedding:
        existing = await self.get_by_source(source_type, source_id)
        if existing is not None:
            existing.content = content
            existing.embedding = vector
            existing.model = model
            existing.dimensions = dimensions
            await self._session.commit()
            await self._session.refresh(existing)
            return existing

        embedding = Embedding(
            source_type=source_type,
            source_id=source_id,
            content=content,
            embedding=vector,
            model=model,
            dimensions=dimensions,
        )
        self._session.add(embedding)
        await self._session.commit()
        await self._session.refresh(embedding)
        return embedding

    async def search(
        self,
        query_vector: list[float],
        source_types: list[str] | None,
        limit: int,
        threshold: float,
    ) -> list[tuple[Embedding, float]]:
        distance_col = Embedding.embedding.cosine_distance(query_vector)
        query = select(Embedding, (1 - distance_col).label("similarity")).where(
            distance_col <= (1 - threshold)
        )
        if source_types:
            query = query.where(Embedding.source_type.in_(source_types))
        query = (
            query
            .outerjoin(Memory, and_(Embedding.source_type == "memory", Embedding.source_id == Memory.id))
            .where(
                or_(
                    Embedding.source_type != "memory",
                    and_(
                        Memory.active.is_(True),
                        or_(Memory.expires_at.is_(None), Memory.expires_at > func.now()),
                    ),
                )
            )
            .order_by(distance_col)
            .limit(limit)
        )

        result = await self._session.execute(query)
        return [(row.Embedding, row.similarity) for row in result]

    async def delete(self, embedding_id: int) -> bool:
        embedding = await self.get(embedding_id)
        if embedding is None:
            return False
        await self._session.delete(embedding)
        await self._session.commit()
        return True
