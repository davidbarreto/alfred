from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.study.tracks.tables import StudyTrack


class StudyTrackRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_track(self, track_id: int) -> StudyTrack | None:
        result = await self._session.execute(select(StudyTrack).where(StudyTrack.id == track_id))
        return result.scalars().first()

    async def get_track_by_name(self, name: str) -> StudyTrack | None:
        result = await self._session.execute(select(StudyTrack).where(StudyTrack.name == name))
        return result.scalars().first()

    async def get_tracks(self) -> list[StudyTrack]:
        result = await self._session.execute(select(StudyTrack).order_by(StudyTrack.name))
        return list(result.scalars().all())
