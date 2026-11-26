from datetime import date

from sqlalchemy import Date, Select, cast, func, or_, select, union, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.location.countries.tables import Country
from app.features.location.places.tables import Place
from app.features.travel.places.schemas import TravelPlaceFilters
from app.features.travel.stays.tables import Stay
from app.features.travel.tags.tables import TravelTag, places_tags
from app.features.travel.visits.tables import Visit


def _grades():
    """Every grade given to a place, from visits and stays alike."""
    visits = select(Visit.place_id.label("place_id"), Visit.grade.label("grade")).where(Visit.grade.is_not(None))
    stays = select(Stay.place_id.label("place_id"), Stay.grade.label("grade")).where(Stay.grade.is_not(None))
    return union_all(visits, stays).subquery()


def visited_place_ids():
    """Places been to: a visited visit, or a stay that has begun."""
    return union(
        select(Visit.place_id).where(Visit.status == "visited"),
        select(Stay.place_id).where(Stay.check_in_at <= func.now()),
    )


def planned_place_ids():
    """Places with something ahead (a planned visit or a future stay); a place may be visited too."""
    return union(
        select(Visit.place_id).where(Visit.status == "planned"),
        select(Stay.place_id).where(Stay.check_in_at > func.now()),
    )


def _with_status(stmt: Select, status: str) -> Select:
    """Visited places, or planned ones that are not visited (a place in both is visited only)."""
    if status == "visited":
        return stmt.where(Place.id.in_(visited_place_ids()))
    return stmt.where(Place.id.in_(planned_place_ids()), ~Place.id.in_(visited_place_ids()))


class TravelPlaceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_place(self, place_id: int) -> Place | None:
        return await self._session.get(Place, place_id)

    async def get_places(self, filters: TravelPlaceFilters) -> list[Place]:
        stmt = select(Place).join(City, City.id == Place.city_id).join(Country, Country.id == City.country_id)
        if filters.q:
            pattern = f"%{filters.q.strip().lower()}%"
            stmt = stmt.where(
                or_(*(func.lower(col).like(pattern) for col in (Place.name, City.name, Country.name, Place.address)))
            )
        if filters.kind:
            stmt = stmt.where(Place.kind == filters.kind)
        if filters.city:
            stmt = stmt.where(func.lower(City.name) == filters.city.strip().lower())
        if filters.country:
            stmt = stmt.where(func.lower(Country.name) == filters.country.strip().lower())
        if filters.city_id is not None:
            stmt = stmt.where(Place.city_id == filters.city_id)
        if filters.country_id is not None:
            stmt = stmt.where(City.country_id == filters.country_id)
        for tag_name in filters.tag or []:
            tagged = (
                select(places_tags.c.place_id)
                .join(TravelTag, TravelTag.id == places_tags.c.tag_id)
                .where(func.lower(TravelTag.name) == tag_name.strip().lower())
            )
            stmt = stmt.where(Place.id.in_(tagged))
        if filters.min_grade is not None:
            grades = _grades()
            good = select(grades.c.place_id).group_by(grades.c.place_id).having(func.avg(grades.c.grade) >= filters.min_grade)
            stmt = stmt.where(Place.id.in_(good))
        if filters.ungraded:
            stmt = stmt.where(~Place.id.in_(select(_grades().c.place_id)))
        if filters.status:
            stmt = _with_status(stmt, filters.status)
        if filters.no_trip:
            stmt = stmt.where(
                ~Place.id.in_(select(Visit.place_id).where(Visit.trip_id.is_not(None))),
                ~Place.id.in_(select(Stay.place_id).where(Stay.trip_id.is_not(None))),
            )
        if filters.active is not None:
            stmt = stmt.where(Place.active.is_(filters.active))
        stmt = stmt.order_by(func.lower(Place.name), Place.id).limit(filters.limit).offset(filters.offset)
        return list((await self._session.scalars(stmt)).all())

    async def get_locations(self) -> tuple[list[str], list[str]]:
        """Distinct cities and countries over all places, sorted case-insensitively."""
        stmt = select(City.name, Country.name).join(Country, Country.id == City.country_id).where(
            City.id.in_(select(Place.city_id))
        )
        rows = (await self._session.execute(stmt)).all()
        cities = {city for city, _ in rows}
        countries = {country for _, country in rows}
        return sorted(cities, key=str.casefold), sorted(countries, key=str.casefold)

    async def get_grades(self, place_ids: list[int]) -> dict[int, tuple[float, int]]:
        """Average grade and how many grades went into it, for places that have any."""
        if not place_ids:
            return {}
        grades = _grades()
        stmt = (
            select(grades.c.place_id, func.avg(grades.c.grade), func.count())
            .where(grades.c.place_id.in_(place_ids))
            .group_by(grades.c.place_id)
        )
        return {pid: (round(float(avg), 2), int(n)) for pid, avg, n in (await self._session.execute(stmt)).all()}

    async def get_last_visits(self, place_ids: list[int]) -> dict[int, date]:
        """The latest day each place was been to: a visited visit's date or a begun stay's check-in day (in its zone)."""
        if not place_ids:
            return {}
        visits = select(Visit.place_id.label("place_id"), Visit.visit_date.label("day")).where(
            Visit.status == "visited", Visit.visit_date.is_not(None)
        )
        stays = select(
            Stay.place_id.label("place_id"), cast(func.timezone(Stay.timezone, Stay.check_in_at), Date).label("day")
        ).where(Stay.check_in_at <= func.now())
        days = union_all(visits, stays).subquery()
        stmt = select(days.c.place_id, func.max(days.c.day)).where(days.c.place_id.in_(place_ids)).group_by(days.c.place_id)
        return {pid: day for pid, day in (await self._session.execute(stmt)).all()}

    async def set_tags(self, place: Place, tags: list[TravelTag]) -> None:
        place.tags = tags
        await self._session.commit()
        await self._session.refresh(place)
