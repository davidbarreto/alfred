from datetime import date, datetime

from sqlalchemy import func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.location.places.tables import Place
from app.features.travel.legs.tables import Leg
from app.features.travel.links.tables import WebLink
from app.features.travel.stays.tables import Stay
from app.features.travel.trips.tables import Trip
from app.features.travel.visits.tables import Visit


class TravelCityRepository:
    """Travel's queries about a city: its places, trips and leg ends."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def attach_leg_ends(self, city: City) -> int:
        """Point every leg end with no city whose text equals the city's name at it. Returns the ends attached."""
        key = city.name.strip().lower()
        attached = 0
        for text_col, city_col in ((Leg.origin, Leg.origin_city_id), (Leg.destination, Leg.destination_city_id)):
            result = await self._session.execute(
                update(Leg).where(city_col.is_(None), func.lower(func.trim(text_col)) == key).values({city_col.key: city.id})
            )
            attached += result.rowcount or 0
        return attached

    async def get_place_ids_by_city(self, city_ids: list[int]) -> dict[int, list[int]]:
        """City id -> ids of its places (a city with none maps to an empty list)."""
        found: dict[int, list[int]] = {i: [] for i in city_ids}
        if city_ids:
            for city_id, place_id in (await self._session.execute(
                select(Place.city_id, Place.id).where(Place.city_id.in_(city_ids)).order_by(Place.id)
            )).all():
                found[city_id].append(place_id)
        return found

    async def get_places(self, place_ids: list[int], limit: int) -> list[Place]:
        """The first `limit` of the places, by name."""
        if not place_ids:
            return []
        stmt = select(Place).where(Place.id.in_(place_ids)).order_by(func.lower(Place.name), Place.id).limit(limit)
        return list((await self._session.scalars(stmt)).all())

    async def get_trips_of_cities(self, city_ids: list[int]) -> list[Trip]:
        """Trips with a stay or visit at a place in the cities, or a leg end in them, newest first."""
        if not city_ids:
            return []
        in_places = select(Place.id).where(Place.city_id.in_(city_ids))
        trip_ids = union(
            select(Stay.trip_id).where(Stay.place_id.in_(in_places), Stay.trip_id.is_not(None)),
            select(Visit.trip_id).where(Visit.place_id.in_(in_places), Visit.trip_id.is_not(None)),
            select(Leg.trip_id).where(or_(Leg.origin_city_id.in_(city_ids), Leg.destination_city_id.in_(city_ids))),
        )
        stmt = select(Trip).where(Trip.id.in_(trip_ids)).order_by(Trip.start_date.desc(), Trip.id.desc())
        return list((await self._session.scalars(stmt)).all())

    async def get_stay_spans(self, city_ids: list[int]) -> list[tuple[int, datetime, datetime, str]]:
        """(city id, check-in, check-out, zone) of every stay at a place in the cities."""
        if not city_ids:
            return []
        stmt = (
            select(Place.city_id, Stay.check_in_at, Stay.check_out_at, Stay.timezone)
            .join(Place, Stay.place_id == Place.id).where(Place.city_id.in_(city_ids))
        )
        return [tuple(row) for row in (await self._session.execute(stmt)).all()]

    async def get_stays(self, city_ids: list[int], limit: int, offset: int) -> list[Stay]:
        """Stays at places in the cities, newest check-in first."""
        if not city_ids:
            return []
        in_places = select(Place.id).where(Place.city_id.in_(city_ids))
        stmt = (
            select(Stay).where(Stay.place_id.in_(in_places))
            .order_by(Stay.check_in_at.desc(), Stay.id.desc()).limit(limit).offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def count_stays(self, city_ids: list[int]) -> int:
        if not city_ids:
            return 0
        in_places = select(Place.id).where(Place.city_id.in_(city_ids))
        return int(await self._session.scalar(select(func.count()).select_from(Stay).where(Stay.place_id.in_(in_places))) or 0)

    async def get_legs(self, city_id: int, limit: int, offset: int) -> list[Leg]:
        """Legs that start or end in the city, newest departure first."""
        stmt = (
            select(Leg).where(or_(Leg.origin_city_id == city_id, Leg.destination_city_id == city_id))
            .order_by(Leg.departs_at.desc(), Leg.id.desc()).limit(limit).offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_trip_names(self, trip_ids: set[int]) -> dict[int, str]:
        if not trip_ids:
            return {}
        stmt = select(Trip.id, Trip.name).where(Trip.id.in_(sorted(trip_ids)))
        return {trip_id: name for trip_id, name in (await self._session.execute(stmt)).all()}

    async def count_leg_ends(self, city_id: int) -> int:
        stmt = select(func.count()).select_from(Leg).where(or_(Leg.origin_city_id == city_id, Leg.destination_city_id == city_id))
        return int(await self._session.scalar(stmt) or 0)

    async def count_places(self, city_id: int) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(Place).where(Place.city_id == city_id)) or 0)

    async def get_travel_city_ids(self) -> set[int]:
        """Cities with travel data: a stay or visit at one of their places, a leg end, or a link."""
        stmt = union(
            select(Place.city_id).where(Place.id.in_(select(Stay.place_id))),
            select(Place.city_id).where(Place.id.in_(select(Visit.place_id))),
            select(Leg.origin_city_id).where(Leg.origin_city_id.is_not(None)),
            select(Leg.destination_city_id).where(Leg.destination_city_id.is_not(None)),
            select(WebLink.city_id).where(WebLink.city_id.is_not(None)),
        )
        return set((await self._session.scalars(stmt)).all())

    async def get_link_country_ids(self) -> set[int]:
        stmt = select(WebLink.country_id).where(WebLink.country_id.is_not(None)).distinct()
        return set((await self._session.scalars(stmt)).all())

    async def get_trip_city_pairs(self, city_ids: list[int]) -> list[tuple[int, int]]:
        """(trip id, city id) for every trip with a stay, a visit or a leg end in one of the cities."""
        if not city_ids:
            return []
        stmt = union(
            select(Stay.trip_id, Place.city_id).join(Place, Stay.place_id == Place.id)
            .where(Stay.trip_id.is_not(None), Place.city_id.in_(city_ids)),
            select(Visit.trip_id, Place.city_id).join(Place, Visit.place_id == Place.id)
            .where(Visit.trip_id.is_not(None), Place.city_id.in_(city_ids)),
            select(Leg.trip_id, Leg.origin_city_id).where(Leg.origin_city_id.in_(city_ids)),
            select(Leg.trip_id, Leg.destination_city_id).where(Leg.destination_city_id.in_(city_ids)),
        )
        return [(trip_id, city_id) for trip_id, city_id in (await self._session.execute(stmt)).all()]

    async def get_trips(self, trip_ids: set[int]) -> list[Trip]:
        if not trip_ids:
            return []
        return list((await self._session.scalars(select(Trip).where(Trip.id.in_(sorted(trip_ids))))).all())

    async def get_last_local_visits(self, city_ids: list[int], today: date) -> dict[int, date]:
        """City id -> the latest day something was done there (a visited visit, or a stay begun), up to `today`."""
        if not city_ids:
            return {}
        visits = (
            select(Place.city_id, func.max(Visit.visit_date)).join(Place, Visit.place_id == Place.id)
            .where(Place.city_id.in_(city_ids), Visit.status == "visited", Visit.visit_date <= today)
            .group_by(Place.city_id)
        )
        stays = (
            select(Place.city_id, func.max(func.date(Stay.check_in_at))).join(Place, Stay.place_id == Place.id)
            .where(Place.city_id.in_(city_ids), func.date(Stay.check_in_at) <= today)
            .group_by(Place.city_id)
        )
        found: dict[int, date] = {}
        for stmt in (visits, stays):
            for city_id, day in (await self._session.execute(stmt)).all():
                if day is not None and (city_id not in found or day > found[city_id]):
                    found[city_id] = day
        return found
