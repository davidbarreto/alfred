from __future__ import annotations

from sqlalchemy import case, delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.places.constants import HOME_KIND
from app.features.location.places.tables import Place
from app.features.organizer.everyday_places.schemas import EverydayPlaceFilters
from app.features.organizer.everyday_places.tables import EverydayPlace, places_shopping_categories
from app.features.organizer.shopping_categories.tables import ShoppingCategory


def _is_everyday():
    """Members plus the Home place, which is always everyday."""
    return or_(Place.kind == HOME_KIND, Place.id.in_(select(EverydayPlace.place_id)))


class EverydayPlaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, filters: EverydayPlaceFilters) -> list[Place]:
        stmt = select(Place).where(_is_everyday()).execution_options(populate_existing=True)
        if filters.kind:
            stmt = stmt.where(Place.kind == filters.kind)
        if filters.active is not None:
            stmt = stmt.where(Place.active.is_(filters.active))
        if filters.city_id is not None:
            stmt = stmt.where(Place.city_id == filters.city_id)
        if filters.category_id is not None:
            stmt = stmt.where(
                Place.id.in_(
                    select(places_shopping_categories.c.place_id).where(
                        places_shopping_categories.c.category_id == filters.category_id
                    )
                )
            )
        if filters.q:
            pattern = f"%{filters.q.lower()}%"
            stmt = stmt.where(or_(func.lower(Place.name).like(pattern), func.lower(Place.address).like(pattern)))
        stmt = (
            stmt.order_by(case((Place.kind == HOME_KIND, 0), else_=1), func.lower(Place.name), Place.id)
            .limit(filters.limit)
            .offset(filters.offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def members(self, place_ids: list[int]) -> set[int]:
        """Which of these places have an everyday row (Home is everyday without one)."""
        if not place_ids:
            return set()
        stmt = select(EverydayPlace.place_id).where(EverydayPlace.place_id.in_(place_ids))
        return set((await self._session.scalars(stmt)).all())

    async def add_member(self, place_id: int) -> bool:
        """Add the membership without committing; False when it was already there."""
        if await self._session.get(EverydayPlace, place_id) is not None:
            return False
        self._session.add(EverydayPlace(place_id=place_id))
        await self._session.flush()
        return True

    async def remove_member(self, place_id: int) -> bool:
        result = await self._session.execute(delete(EverydayPlace).where(EverydayPlace.place_id == place_id))
        return bool(result.rowcount)

    async def categories_of(self, place_ids: list[int]) -> dict[int, list[ShoppingCategory]]:
        """What each place sells, by name."""
        if not place_ids:
            return {}
        stmt = (
            select(places_shopping_categories.c.place_id, ShoppingCategory)
            .join(ShoppingCategory, ShoppingCategory.id == places_shopping_categories.c.category_id)
            .where(places_shopping_categories.c.place_id.in_(place_ids))
            .order_by(ShoppingCategory.name)
        )
        found: dict[int, list[ShoppingCategory]] = {}
        for place_id, category in (await self._session.execute(stmt)).all():
            found.setdefault(place_id, []).append(category)
        return found

    async def set_categories(self, place_id: int, category_ids: list[int]) -> None:
        """Replace what the place sells, without committing."""
        await self._session.execute(
            delete(places_shopping_categories).where(places_shopping_categories.c.place_id == place_id)
        )
        if category_ids:
            await self._session.execute(
                insert(places_shopping_categories),
                [{"place_id": place_id, "category_id": category_id} for category_id in category_ids],
            )
        await self._session.flush()

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

    async def commit(self) -> None:
        await self._session.commit()
