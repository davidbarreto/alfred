import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.study.tracks.repository import StudyTrackRepository
from app.features.study.tracks.schemas import StudyTrackRead

logger = logging.getLogger(__name__)

# Seeded by migration 070; the only track until a second study domain exists.
SOFTWARE_ENGINEERING_TRACK = "Software Engineering"


class StudyTrackService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StudyTrackRepository(session)

    async def get_track(self, track_id: int) -> StudyTrackRead | None:
        orm = await self._repo.get_track(track_id)
        return StudyTrackRead.model_validate(orm) if orm else None

    async def get_track_by_name(self, name: str) -> StudyTrackRead | None:
        orm = await self._repo.get_track_by_name(name)
        if orm is None:
            logger.debug("Study track lookup: name=%r not found", name)
            return None
        return StudyTrackRead.model_validate(orm)

    async def get_tracks(self) -> list[StudyTrackRead]:
        orms = await self._repo.get_tracks()
        return [StudyTrackRead.model_validate(orm) for orm in orms]
