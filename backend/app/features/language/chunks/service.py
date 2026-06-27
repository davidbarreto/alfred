import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.repository import ChunkRepository
from app.features.language.chunks.schemas import (
    ChunkCreate,
    ChunkFilters,
    ChunkRead,
    ChunkUpdate,
    DailyBatchRead,
)
from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackFilters
from app.features.language.srs import CardState, State, next_card_state, quality_to_rating, is_leech

logger = logging.getLogger(__name__)


class ChunkService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ChunkRepository(session)
        self._track_repo = TrackRepository(session)

    async def get_chunk(self, chunk_id: int) -> ChunkRead | None:
        orm = await self._repo.get_chunk(chunk_id)
        return ChunkRead.model_validate(orm) if orm else None

    async def get_chunks(self, filters: ChunkFilters) -> list[ChunkRead]:
        chunks = await self._repo.get_chunks(filters)
        return [ChunkRead.model_validate(c) for c in chunks]

    async def count_chunks(self, filters: ChunkFilters) -> int:
        return await self._repo.count_chunks(filters)

    async def create_chunk(self, data: ChunkCreate) -> ChunkRead:
        orm = await self._repo.create_chunk(data)
        logger.info("Chunk created: id=%d track_id=%d type=%r", orm.id, orm.track_id, orm.chunk_type)
        return ChunkRead.model_validate(orm)

    async def update_chunk(self, chunk_id: int, data: ChunkUpdate) -> ChunkRead | None:
        orm = await self._repo.update_chunk(chunk_id, data)
        if orm is None:
            return None
        logger.info("Chunk updated: id=%d", chunk_id)
        return ChunkRead.model_validate(orm)

    async def delete_chunk(self, chunk_id: int) -> None:
        await self._repo.delete_chunk(chunk_id)
        logger.info("Chunk deleted: id=%d", chunk_id)

    async def approve_chunk(self, chunk_id: int) -> ChunkRead | None:
        """Move a pending_triage chunk to active."""
        orm = await self._repo.get_chunk(chunk_id)
        if orm is None:
            return None
        update_data = ChunkUpdate(status="active")
        return await self.update_chunk(chunk_id, update_data)

    async def apply_srs_review(self, chunk_id: int, quality_score: float) -> ChunkRead | None:
        """Update FSRS state for a chunk after a review session."""
        orm = await self._repo.get_chunk(chunk_id)
        if orm is None:
            return None

        card = CardState(
            stability=orm.stability,
            difficulty=orm.difficulty,
            due_at=orm.due_at,
            last_review_at=orm.last_review_at,
            repetitions=orm.repetitions,
            lapses=orm.lapses,
            consecutive_failures=orm.consecutive_failures,
            state=orm.state,
        )
        rating = quality_to_rating(quality_score)
        now = datetime.now(timezone.utc)
        new_card = next_card_state(card, rating, now)
        leech = is_leech(new_card.consecutive_failures)

        await self._repo.update_srs_fields(
            chunk_id=chunk_id,
            stability=new_card.stability,
            difficulty=new_card.difficulty,
            due_at=new_card.due_at,
            last_review_at=new_card.last_review_at,
            repetitions=new_card.repetitions,
            lapses=new_card.lapses,
            consecutive_failures=new_card.consecutive_failures,
            state=new_card.state,
            is_leech=leech,
        )

        if leech and not orm.is_leech:
            logger.warning("Chunk flagged as leech: id=%d consecutive_failures=%d", chunk_id, new_card.consecutive_failures)

        updated = await self._repo.get_chunk(chunk_id)
        return ChunkRead.model_validate(updated)

    async def get_daily_batch(self, track_id: int | None = None) -> list[DailyBatchRead]:
        """Return today's review batches per active track, Pareto-weighted."""
        tracks_query = await self._track_repo.get_tracks(
            TrackFilters(active_only=True)
        )
        if track_id is not None:
            tracks_query = [t for t in tracks_query if t.id == track_id]

        batches = []
        for track in tracks_query:
            total_due = await self._repo.count_due_for_track(track.id)
            chunks_orm = await self._repo.get_due_chunks_for_track(track.id, track.daily_quota)
            batches.append(DailyBatchRead(
                track_id=track.id,
                track_code=track.code,
                chunks=[ChunkRead.model_validate(c) for c in chunks_orm],
                total_due=total_due,
            ))
        return batches
