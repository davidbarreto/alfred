from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.location.countries.tables import Country
from app.features.location.places.constants import HOME_KIND
from app.features.location.places.schemas import PlaceFilters
from app.features.location.places.tables import Place


def normalized(name: str) -> str:
    """A name as compared: inner whitespace collapsed, lowercase."""
    return " ".join(name.split()).lower()


class PlaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _select(self):
        return select(Place).execution_options(populate_existing=True)

    async def get(self, place_id: int) -> Place | None:
        return await self._session.scalar(self._select().where(Place.id == place_id))

    async def get_many(self, place_ids: list[int]) -> list[Place]:
        if not place_ids:
            return []
        return list((await self._session.scalars(self._select().where(Place.id.in_(place_ids)))).all())

    async def get_by_name(self, name: str, city_id: int | None = None) -> list[Place]:
        """Places with this name (case-insensitive), in one city when `city_id` is given; oldest first."""
        stmt = self._select().where(func.lower(Place.name) == normalized(name))
        if city_id is not None:
            stmt = stmt.where(Place.city_id == city_id)
        return list((await self._session.scalars(stmt.order_by(Place.id))).all())

    async def names(self) -> dict[int, str]:
        return {pid: name for pid, name in (await self._session.execute(select(Place.id, Place.name))).all()}

    async def get_home(self) -> Place | None:
        return await self._session.scalar(self._select().where(Place.kind == HOME_KIND))

    async def city_exists(self, city_id: int) -> bool:
        return await self._session.get(City, city_id) is not None

    async def list(self, filters: PlaceFilters) -> list[Place]:
        stmt = self._select().join(City, City.id == Place.city_id).join(Country, Country.id == City.country_id)
        if filters.kind:
            stmt = stmt.where(Place.kind == filters.kind)
        if filters.city_id is not None:
            stmt = stmt.where(Place.city_id == filters.city_id)
        if filters.country_id is not None:
            stmt = stmt.where(City.country_id == filters.country_id)
        if filters.active is not None:
            stmt = stmt.where(Place.active.is_(filters.active))
        if filters.q:
            pattern = f"%{filters.q.lower()}%"
            stmt = stmt.where(
                or_(*(func.lower(col).like(pattern) for col in (Place.name, Place.address, City.name, Country.name)))
            )
        stmt = (
            stmt.order_by(case((Place.kind == HOME_KIND, 0), else_=1), func.lower(Place.name), Place.id)
            .limit(filters.limit)
            .offset(filters.offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def add(self, fields: dict[str, Any]) -> Place:
        """Insert without committing: the caller commits (with its own rows, such as an everyday membership)."""
        place = Place(**fields)
        self._session.add(place)
        await self._session.flush()
        return place

    async def update(self, place: Place, fields: dict[str, Any]) -> None:
        for field, value in fields.items():
            setattr(place, field, value)
        await self._session.flush()

    async def delete(self, place: Place) -> None:
        await self._session.delete(place)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
