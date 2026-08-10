import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.chunks.service import ChunkService
from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackCreate, TrackFilters, TrackRead, TrackUpdate

logger = logging.getLogger(__name__)


class TrackService:

    def __init__(self, session: AsyncSession, chunk_service: ChunkService | None = None) -> None:
        self._repo = TrackRepository(session)
        self._chunk_service = chunk_service or ChunkService(session)

    async def get_track(self, track_id: int) -> TrackRead | None:
        orm = await self._repo.get_track(track_id)
        return TrackRead.model_validate(orm) if orm else None

    async def get_tracks(self, filters: TrackFilters) -> list[TrackRead]:
        tracks = await self._repo.get_tracks(filters)
        return [TrackRead.model_validate(t) for t in tracks]

    async def create_track(self, data: TrackCreate) -> TrackRead:
        orm = await self._repo.create_track(data)
        logger.info("Track created: id=%d code=%r", orm.id, orm.code)
        return TrackRead.model_validate(orm)

    async def update_track(self, track_id: int, data: TrackUpdate) -> TrackRead | None:
        orm = await self._repo.update_track(track_id, data)
        if orm is None:
            return None
        logger.info("Track updated: id=%d", track_id)
        return TrackRead.model_validate(orm)

    async def delete_track(self, track_id: int) -> None:
        await self._repo.delete_track(track_id)
        logger.info("Track deleted: id=%d", track_id)

    async def pause_track(self, track_id: int) -> TrackRead:
        orm = await self._repo.pause_track(track_id)
        if orm is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
        logger.info("Track paused: id=%d code=%r", orm.id, orm.code)
        return TrackRead.model_validate(orm)

    async def resume_track(self, track_id: int) -> TrackRead:
        track = await self._repo.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
        if track.paused_at is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Track is not paused")

        paused_at = track.paused_at
        now = datetime.now(timezone.utc)
        delta = now - paused_at
        await self._chunk_service.shift_due_dates(track_id, delta)

        orm = await self._repo.resume_track(track_id)
        logger.info("Track resumed: id=%d code=%r delta_days=%.2f", orm.id, orm.code, delta.total_seconds() / 86400)
        return TrackRead.model_validate(orm)
