from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.tables import Chunk
from app.features.language.chunks.schemas import ChunkCreate, ChunkUpdate, ChunkFilters


class ChunkRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_chunk(self, chunk_id: int) -> Chunk | None:
        result = await self._session.execute(select(Chunk).where(Chunk.id == chunk_id))
        return result.scalars().first()

    async def get_chunks(self, filters: ChunkFilters) -> list[Chunk]:
        query = select(Chunk)
        if filters.track_id is not None:
            query = query.where(Chunk.track_id == filters.track_id)
        if filters.status != "ALL":
            query = query.where(Chunk.status == filters.status)
        if filters.chunk_type is not None:
            query = query.where(Chunk.chunk_type == filters.chunk_type)
        if filters.is_leech is not None:
            query = query.where(Chunk.is_leech == filters.is_leech)
        if filters.due_only:
            query = query.where(Chunk.due_at <= func.now())
        query = query.order_by(Chunk.due_at.asc()).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_due_chunks_for_track(self, track_id: int, limit: int) -> list[Chunk]:
        """Return active due chunks ordered by Pareto priority (NULL rank first, then ASC)."""
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(Chunk)
            .where(
                Chunk.track_id == track_id,
                Chunk.status == "active",
                Chunk.due_at <= now,
            )
            .order_by(
                Chunk.frequency_rank.asc().nulls_first(),
                Chunk.due_at.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_due_for_track(self, track_id: int) -> int:
        now = datetime.now(timezone.utc)
        result = await self._session.execute(
            select(func.count(Chunk.id)).where(
                Chunk.track_id == track_id,
                Chunk.status == "active",
                Chunk.due_at <= now,
            )
        )
        return result.scalar_one()

    async def create_chunk(self, data: ChunkCreate) -> Chunk:
        chunk = Chunk(**data.model_dump())
        self._session.add(chunk)
        await self._session.commit()
        await self._session.refresh(chunk)
        return chunk

    async def update_chunk(self, chunk_id: int, data: ChunkUpdate) -> Chunk | None:
        chunk = await self.get_chunk(chunk_id)
        if chunk is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(chunk, field, value)
        await self._session.commit()
        await self._session.refresh(chunk)
        return chunk

    async def update_srs_fields(
        self,
        chunk_id: int,
        stability: float,
        difficulty: float,
        due_at: datetime,
        last_review_at: datetime,
        repetitions: int,
        lapses: int,
        consecutive_failures: int,
        state: str,
        is_leech: bool,
    ) -> None:
        await self._session.execute(
            update(Chunk)
            .where(Chunk.id == chunk_id)
            .values(
                stability=stability,
                difficulty=difficulty,
                due_at=due_at,
                last_review_at=last_review_at,
                repetitions=repetitions,
                lapses=lapses,
                consecutive_failures=consecutive_failures,
                state=state,
                is_leech=is_leech,
            )
        )
        await self._session.commit()

    async def delete_chunk(self, chunk_id: int) -> None:
        chunk = await self.get_chunk(chunk_id)
        if chunk:
            await self._session.delete(chunk)
            await self._session.commit()
