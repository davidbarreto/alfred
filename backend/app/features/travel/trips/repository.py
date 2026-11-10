from datetime import date
from typing import Any

from sqlalchemy import and_, case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.tags.tables import TravelTag, trips_tags
from app.features.travel.trips.schemas import TripFilters
from app.features.travel.trips.tables import Trip


class TripRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_trip(self, trip_id: int) -> Trip | None:
        return await self._session.get(Trip, trip_id)

    async def get_trips(self, filters: TripFilters, today: date) -> list[Trip]:
        stmt = select(Trip)
        past = Trip.end_date < today
        if filters.status == "current":
            stmt = stmt.where(~past)
        elif filters.status == "upcoming":
            stmt = stmt.where(Trip.start_date > today)
        elif filters.status == "ongoing":
            stmt = stmt.where(and_(Trip.start_date <= today, Trip.end_date >= today))
        elif filters.status == "past":
            stmt = stmt.where(past)
        if filters.q:
            stmt = stmt.where(func.lower(Trip.name).like(f"%{filters.q.strip().lower()}%"))
        if filters.date_from:
            stmt = stmt.where(Trip.end_date >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Trip.start_date <= filters.date_to)
        for tag_name in filters.tag or []:
            tagged = (
                select(trips_tags.c.trip_id)
                .join(TravelTag, TravelTag.id == trips_tags.c.tag_id)
                .where(func.lower(TravelTag.name) == tag_name.strip().lower())
            )
            stmt = stmt.where(Trip.id.in_(tagged))
        # Upcoming and ongoing first, soonest start first; past trips after them, most recent first.
        stmt = (
            stmt.order_by(
                case((past, 1), else_=0),
                case((past, None), else_=Trip.start_date).asc(),
                case((past, Trip.start_date), else_=None).desc(),
                Trip.id,
            )
            .limit(filters.limit)
            .offset(filters.offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def create_trip(self, data: dict[str, Any], tags: list[TravelTag]) -> Trip:
        trip = Trip(**data)
        trip.tags = tags
        self._session.add(trip)
        await self._session.commit()
        await self._session.refresh(trip)
        return trip

    async def update_trip(self, trip: Trip, data: dict[str, Any], tags: list[TravelTag] | None) -> Trip:
        for field, value in data.items():
            setattr(trip, field, value)
        if tags is not None:
            trip.tags = tags
        await self._session.commit()
        await self._session.refresh(trip)
        return trip

    async def delete_trip(self, trip_id: int) -> bool:
        """Legs go with the trip (CASCADE); stays and visits are detached (SET NULL) so notes survive."""
        result = await self._session.execute(delete(Trip).where(Trip.id == trip_id))
        await self._session.commit()
        return result.rowcount > 0
