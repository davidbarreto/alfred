from typing import Any

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.places.schemas import PlaceFilters
from app.features.travel.places.tables import Place
from app.features.travel.stays.tables import Stay
from app.features.travel.tags.tables import TravelTag, places_tags
from app.features.travel.visits.tables import Visit


def _grades():
    """Every grade given to a place, from visits and stays alike."""
    visits = select(Visit.place_id.label("place_id"), Visit.grade.label("grade")).where(Visit.grade.is_not(None))
    stays = select(Stay.place_id.label("place_id"), Stay.grade.label("grade")).where(Stay.grade.is_not(None))
    return union_all(visits, stays).subquery()


class PlaceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_place(self, place_id: int) -> Place | None:
        return await self._session.get(Place, place_id)

    async def get_places(self, filters: PlaceFilters) -> list[Place]:
        stmt = select(Place)
        if filters.q:
            pattern = f"%{filters.q.strip().lower()}%"
            stmt = stmt.where(
                or_(*(func.lower(col).like(pattern) for col in (Place.name, Place.city, Place.country, Place.address)))
            )
        if filters.kind:
            stmt = stmt.where(Place.kind == filters.kind)
        if filters.city:
            stmt = stmt.where(func.lower(Place.city) == filters.city.strip().lower())
        if filters.country:
            stmt = stmt.where(func.lower(Place.country) == filters.country.strip().lower())
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
        if filters.status:
            stmt = stmt.where(Place.id.in_(select(Visit.place_id).where(Visit.status == filters.status)))
        if filters.no_trip:
            stmt = stmt.where(
                ~Place.id.in_(select(Visit.place_id).where(Visit.trip_id.is_not(None))),
                ~Place.id.in_(select(Stay.place_id).where(Stay.trip_id.is_not(None))),
            )
        stmt = stmt.order_by(func.lower(Place.name), Place.id).limit(filters.limit).offset(filters.offset)
        return list((await self._session.scalars(stmt)).all())

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

    async def create_place(self, data: dict[str, Any], tags: list[TravelTag]) -> Place:
        place = Place(**data)
        place.tags = tags
        self._session.add(place)
        await self._session.commit()
        await self._session.refresh(place)
        return place

    async def update_place(self, place_id: int, data: dict[str, Any], tags: list[TravelTag] | None) -> Place | None:
        place = await self.get_place(place_id)
        if place is None:
            return None
        for field, value in data.items():
            setattr(place, field, value)
        if tags is not None:
            place.tags = tags
        await self._session.commit()
        await self._session.refresh(place)
        return place

    async def delete_place(self, place_id: int) -> bool:
        place = await self.get_place(place_id)
        if place is None:
            return False
        await self._session.delete(place)
        await self._session.commit()
        return True
