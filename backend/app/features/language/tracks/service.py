import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.tracks.repository import TrackRepository
from app.features.language.tracks.schemas import TrackCreate, TrackFilters, TrackRead, TrackUpdate

logger = logging.getLogger(__name__)


class TrackService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TrackRepository(session)

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
