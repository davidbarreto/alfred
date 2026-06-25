from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.tracks.tables import Track
from app.features.language.tracks.schemas import TrackCreate, TrackUpdate, TrackFilters


class TrackRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_track(self, track_id: int) -> Track | None:
        result = await self._session.execute(select(Track).where(Track.id == track_id))
        return result.scalars().first()

    async def get_track_by_code(self, code: str) -> Track | None:
        result = await self._session.execute(select(Track).where(Track.code == code))
        return result.scalars().first()

    async def get_tracks(self, filters: TrackFilters) -> list[Track]:
        query = select(Track)
        if filters.active_only:
            query = query.where(Track.active.is_(True))
        query = query.order_by(Track.code)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_track(self, data: TrackCreate) -> Track:
        track = Track(**data.model_dump())
        self._session.add(track)
        await self._session.commit()
        await self._session.refresh(track)
        return track

    async def update_track(self, track_id: int, data: TrackUpdate) -> Track | None:
        track = await self.get_track(track_id)
        if track is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(track, field, value)
        await self._session.commit()
        await self._session.refresh(track)
        return track

    async def delete_track(self, track_id: int) -> None:
        track = await self.get_track(track_id)
        if track:
            await self._session.delete(track)
            await self._session.commit()
