from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.places.schemas import PlaceFilters
from app.features.travel.places.tables import Place


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
        stmt = stmt.order_by(func.lower(Place.name), Place.id).limit(filters.limit).offset(filters.offset)
        return list((await self._session.scalars(stmt)).all())

    async def create_place(self, data: dict[str, Any]) -> Place:
        place = Place(**data)
        self._session.add(place)
        await self._session.commit()
        await self._session.refresh(place)
        return place

    async def update_place(self, place_id: int, data: dict[str, Any]) -> Place | None:
        place = await self.get_place(place_id)
        if place is None:
            return None
        for field, value in data.items():
            setattr(place, field, value)
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
