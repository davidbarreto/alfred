from datetime import date
from typing import Any

from sqlalchemy import and_, case, delete, func, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.places.tables import Place
from app.features.travel.stays.tables import Stay
from app.features.travel.tags.tables import TravelTag, trips_tags
from app.features.travel.visits.tables import Visit
from app.features.travel.trips.schemas import TripFilters
from app.features.travel.trips.tables import Trip


class TripRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_trip(self, trip_id: int) -> Trip | None:
        return await self._session.get(Trip, trip_id)

    async def get_trips_overlapping(self, start: date, end: date) -> list[Trip]:
        """Trips whose dates intersect [start, end]."""
        stmt = select(Trip).where(Trip.start_date <= end, Trip.end_date >= start).order_by(Trip.start_date, Trip.id)
        return list((await self._session.scalars(stmt)).all())

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
        for column, wanted in ((Place.city, filters.city), (Place.country, filters.country)):
            if wanted:
                where_place = func.lower(column) == wanted.strip().lower()
                stmt = stmt.where(or_(
                    Trip.id.in_(select(Stay.trip_id).join(Place, Place.id == Stay.place_id).where(where_place)),
                    Trip.id.in_(select(Visit.trip_id).join(Place, Place.id == Visit.place_id).where(where_place)),
                ))
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

    async def get_trip_locations(self, trip_ids: list[int]) -> dict[int, tuple[list[str], list[str]]]:
        """Distinct cities and countries (sorted) of the places each trip stays at or visits."""
        stays = select(Stay.trip_id, Place.city, Place.country).join(Place, Place.id == Stay.place_id)
        visits = select(Visit.trip_id, Place.city, Place.country).join(Place, Place.id == Visit.place_id)
        found = union(stays.where(Stay.trip_id.in_(trip_ids)), visits.where(Visit.trip_id.in_(trip_ids))).subquery()
        cities: dict[int, set[str]] = {i: set() for i in trip_ids}
        countries: dict[int, set[str]] = {i: set() for i in trip_ids}
        for trip_id, city, country in (await self._session.execute(select(found))).all():
            if city:
                cities[trip_id].add(city)
            if country:
                countries[trip_id].add(country)
        return {i: (sorted(cities[i], key=str.casefold), sorted(countries[i], key=str.casefold)) for i in trip_ids}

    async def get_locations(self) -> tuple[list[str], list[str]]:
        """Distinct cities and countries of every place used by a trip's stays or visits."""
        used = union(
            select(Stay.place_id.label("place_id")).where(Stay.trip_id.is_not(None)),
            select(Visit.place_id.label("place_id")).where(Visit.trip_id.is_not(None)),
        ).subquery()
        rows = (await self._session.execute(
            select(Place.city, Place.country).where(Place.id.in_(select(used.c.place_id)))
        )).all()
        cities = {city for city, _ in rows if city}
        countries = {country for _, country in rows if country}
        return sorted(cities, key=str.casefold), sorted(countries, key=str.casefold)

    async def get_trips_in_window(self, first_day: date, last_day: date) -> list[Trip]:
        """Trips that are ongoing or start by `last_day` and have not ended before `first_day`."""
        stmt = (
            select(Trip)
            .where(Trip.end_date >= first_day, Trip.start_date <= last_day)
            .order_by(Trip.start_date, Trip.id)
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
