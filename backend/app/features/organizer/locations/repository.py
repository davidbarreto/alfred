from __future__ import annotations

from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.features.organizer.locations.errors import LocationConflictError
from app.features.organizer.locations.schemas import LocationFilters
from app.features.organizer.locations.tables import HOME_KIND, Location
from app.features.organizer.shopping_categories.tables import ShoppingCategory


class LocationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _select(self):
        return select(Location).options(selectinload(Location.categories)).execution_options(populate_existing=True)

    async def get(self, location_id: int) -> Location | None:
        result = await self._session.execute(self._select().where(Location.id == location_id))
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Location | None:
        result = await self._session.execute(
            self._select().where(func.lower(Location.name) == " ".join(name.split()).lower())
        )
        return result.scalars().first()

    async def get_home(self) -> Location | None:
        result = await self._session.execute(self._select().where(Location.kind == HOME_KIND))
        return result.scalars().first()

    async def list(self, filters: LocationFilters) -> list[Location]:
        query = self._select()
        if filters.kind:
            query = query.where(Location.kind == filters.kind)
        if filters.active is not None:
            query = query.where(Location.active.is_(filters.active))
        if filters.category_id is not None:
            query = query.where(Location.categories.any(ShoppingCategory.id == filters.category_id))
        query = (
            query.order_by(case((Location.kind == HOME_KIND, 0), else_=1), func.lower(Location.name))
            .limit(filters.limit)
            .offset(filters.offset)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_categories(self, category_ids: list[int]) -> list[ShoppingCategory]:
        if not category_ids:
            return []
        result = await self._session.execute(select(ShoppingCategory).where(ShoppingCategory.id.in_(category_ids)))
        return list(result.scalars().all())

    async def get_categories_by_name(self, names: list[str]) -> list[ShoppingCategory]:
        if not names:
            return []
        result = await self._session.execute(
            select(ShoppingCategory).where(func.lower(ShoppingCategory.name).in_([n.lower() for n in names]))
        )
        return list(result.scalars().all())

    async def create(self, fields: dict[str, Any], categories: list[ShoppingCategory]) -> Location:
        location = Location(**fields)
        location.categories = categories
        self._session.add(location)
        await self._commit()
        return await self._require(location.id)

    async def update(
        self, location_id: int, fields: dict[str, Any], categories: list[ShoppingCategory] | None
    ) -> Location | None:
        location = await self.get(location_id)
        if location is None:
            return None
        for field, value in fields.items():
            setattr(location, field, value)
        if categories is not None:
            location.categories = categories
        await self._commit()
        return await self._require(location_id)

    async def delete(self, location: Location) -> None:
        await self._session.delete(location)
        await self._session.commit()

    async def _commit(self) -> None:
        # The service checks name and home clashes first; this catches a race between two writes.
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise LocationConflictError("Another location already has this name, or a home already exists") from exc

    async def _require(self, location_id: int) -> Location:
        location = await self.get(location_id)
        assert location is not None
        return location
