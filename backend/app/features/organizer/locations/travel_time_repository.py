from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.locations.tables import LocationTravelTime


class LocationTravelTimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, travel_time_id: int) -> LocationTravelTime | None:
        result = await self._session.execute(
            select(LocationTravelTime)
            .where(LocationTravelTime.id == travel_time_id)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def list_all(self) -> list[LocationTravelTime]:
        result = await self._session.execute(select(LocationTravelTime).order_by(LocationTravelTime.id))
        return list(result.scalars().all())

    async def list_for(self, location_id: int) -> list[LocationTravelTime]:
        """Every travel time that starts or ends at the location, oldest first."""
        result = await self._session.execute(
            select(LocationTravelTime)
            .where(or_(LocationTravelTime.origin_id == location_id, LocationTravelTime.destination_id == location_id))
            .order_by(LocationTravelTime.id)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(LocationTravelTime)) or 0)

    async def find(self, origin_id: int, destination_id: int, mode: str) -> LocationTravelTime | None:
        result = await self._session.execute(
            select(LocationTravelTime).where(
                LocationTravelTime.origin_id == origin_id,
                LocationTravelTime.destination_id == destination_id,
                LocationTravelTime.mode == mode,
            )
        )
        return result.scalars().first()

    async def save(self, origin_id: int, destination_id: int, mode: str, minutes: int) -> LocationTravelTime:
        """Insert the route, or update its minutes when it exists."""
        travel_time = await self.find(origin_id, destination_id, mode)
        if travel_time is None:
            travel_time = LocationTravelTime(origin_id=origin_id, destination_id=destination_id, mode=mode, minutes=minutes)
            self._session.add(travel_time)
        else:
            travel_time.minutes = minutes
        await self._session.commit()
        saved = await self.get(travel_time.id)
        assert saved is not None
        return saved

    async def replace_all(self, routes: list[tuple[int, int, str, int]]) -> None:
        """Delete every travel time and insert `routes` (origin_id, destination_id, mode, minutes) in one commit."""
        await self._session.execute(delete(LocationTravelTime))
        for origin_id, destination_id, mode, minutes in routes:
            self._session.add(
                LocationTravelTime(origin_id=origin_id, destination_id=destination_id, mode=mode, minutes=minutes)
            )
        await self._session.commit()

    async def delete(self, travel_time: LocationTravelTime) -> None:
        await self._session.delete(travel_time)
        await self._session.commit()
