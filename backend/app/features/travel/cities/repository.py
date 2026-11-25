from sqlalchemy import func, or_, select, union, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.travel.legs.tables import Leg
from app.features.location.places.tables import Place
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

    async def count_leg_ends(self, city_id: int) -> int:
        stmt = select(func.count()).select_from(Leg).where(or_(Leg.origin_city_id == city_id, Leg.destination_city_id == city_id))
        return int(await self._session.scalar(stmt) or 0)

    async def count_places(self, city_id: int) -> int:
        return int(await self._session.scalar(select(func.count()).select_from(Place).where(Place.city_id == city_id)) or 0)
