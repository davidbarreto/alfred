from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.places.tables import Place
from app.features.travel.visits.schemas import VisitFilters
from app.features.travel.visits.tables import Visit

# Undated visits come last, and within a day those without a time come last, in creation order.
_ORDER = (Visit.visit_date.asc().nulls_last(), Visit.visit_time.asc().nulls_last(), Visit.id.asc())


class VisitRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_visit(self, visit_id: int) -> Visit | None:
        return await self._session.get(Visit, visit_id)

    async def get_visits(self, filters: VisitFilters) -> list[Visit]:
        stmt = select(Visit)
        if filters.trip_id is not None:
            stmt = stmt.where(Visit.trip_id == filters.trip_id)
        if filters.no_trip:
            stmt = stmt.where(Visit.trip_id.is_(None))
        if filters.place_id is not None:
            stmt = stmt.where(Visit.place_id == filters.place_id)
        if filters.status:
            stmt = stmt.where(Visit.status == filters.status)
        if filters.date_from:
            stmt = stmt.where(Visit.visit_date >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Visit.visit_date <= filters.date_to)
        stmt = stmt.order_by(*_ORDER).limit(filters.limit).offset(filters.offset)
        return list((await self._session.scalars(stmt)).all())

    async def get_trip_visits(self, trip_id: int) -> list[Visit]:
        stmt = select(Visit).where(Visit.trip_id == trip_id).order_by(*_ORDER)
        return list((await self._session.scalars(stmt)).all())

    async def get_wishlist_in_cities(self, cities: list[str]) -> list[Visit]:
        """Planned visits that belong to no trip (the wishlist) at places in one of the cities, case-insensitive."""
        lowered = [c.lower() for c in cities if c]
        if not lowered:
            return []
        stmt = (
            select(Visit).join(Place, Visit.place_id == Place.id)
            .where(Visit.trip_id.is_(None), Visit.status == "planned", func.lower(Place.city).in_(lowered))
            .order_by(*_ORDER)
        )
        return list((await self._session.scalars(stmt)).all())

    async def get_place_visits(self, place_id: int) -> list[Visit]:
        """History of one place, most recent first (undated last)."""
        stmt = (
            select(Visit)
            .where(Visit.place_id == place_id)
            .order_by(Visit.visit_date.desc().nulls_last(), Visit.id.desc())
        )
        return list((await self._session.scalars(stmt)).all())

    async def create_visit(self, data: dict[str, Any]) -> Visit:
        visit = Visit(**data)
        self._session.add(visit)
        await self._session.commit()
        await self._session.refresh(visit)
        return visit

    async def update_visit(self, visit: Visit, data: dict[str, Any]) -> Visit:
        for field, value in data.items():
            setattr(visit, field, value)
        await self._session.commit()
        await self._session.refresh(visit)
        return visit

    async def delete_visit(self, visit: Visit) -> None:
        await self._session.delete(visit)
        await self._session.commit()
