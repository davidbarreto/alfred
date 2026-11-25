from __future__ import annotations

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.travel_times.tables import TravelTime


class TravelTimeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, travel_time_id: int) -> TravelTime | None:
        result = await self._session.execute(
            select(TravelTime)
            .where(TravelTime.id == travel_time_id)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()

    async def list_all(self) -> list[TravelTime]:
        result = await self._session.execute(select(TravelTime).order_by(TravelTime.id))
        return list(result.scalars().all())

    async def list_for(self, place_id: int) -> list[TravelTime]:
        """Every travel time that starts or ends at the place, oldest first."""
        result = await self._session.execute(
            select(TravelTime)
            .where(or_(TravelTime.origin_place_id == place_id, TravelTime.destination_place_id == place_id))
            .order_by(TravelTime.id)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(TravelTime)) or 0)

    async def find(self, origin_place_id: int, destination_place_id: int, mode: str) -> TravelTime | None:
        result = await self._session.execute(
            select(TravelTime).where(
                TravelTime.origin_place_id == origin_place_id,
                TravelTime.destination_place_id == destination_place_id,
                TravelTime.mode == mode,
            )
        )
        return result.scalars().first()

    async def save(self, origin_place_id: int, destination_place_id: int, mode: str, minutes: int) -> TravelTime:
        """Insert the route, or update its minutes when it exists."""
        travel_time = await self.find(origin_place_id, destination_place_id, mode)
        if travel_time is None:
            travel_time = TravelTime(origin_place_id=origin_place_id, destination_place_id=destination_place_id, mode=mode, minutes=minutes)
            self._session.add(travel_time)
        else:
            travel_time.minutes = minutes
        await self._session.commit()
        saved = await self.get(travel_time.id)
        assert saved is not None
        return saved

    async def replace_all(self, routes: list[tuple[int, int, str, int]]) -> None:
        """Delete every travel time and insert `routes` (origin_place_id, destination_place_id, mode, minutes) in one commit."""
        await self._session.execute(delete(TravelTime))
        for origin_place_id, destination_place_id, mode, minutes in routes:
            self._session.add(
                TravelTime(origin_place_id=origin_place_id, destination_place_id=destination_place_id, mode=mode, minutes=minutes)
            )
        await self._session.commit()

    async def delete(self, travel_time: TravelTime) -> None:
        await self._session.delete(travel_time)
        await self._session.commit()
