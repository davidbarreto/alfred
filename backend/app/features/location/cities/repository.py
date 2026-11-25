from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.schemas import CityFilters
from app.features.location.cities.tables import City


class CityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_city(self, city_id: int) -> City | None:
        return await self._session.get(City, city_id)

    async def get_cities(self, filters: CityFilters) -> list[City]:
        stmt = select(City)
        if filters.country_id is not None:
            stmt = stmt.where(City.country_id == filters.country_id)
        if filters.q and filters.q.strip():
            stmt = stmt.where(func.lower(City.name).like(f"%{filters.q.strip().lower()}%"))
        stmt = stmt.order_by(func.lower(City.name), City.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_country_cities(self, country_id: int) -> list[City]:
        stmt = select(City).where(City.country_id == country_id).order_by(func.lower(City.name), City.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_city_in_country(self, name: str, country_id: int) -> City | None:
        stmt = select(City).where(func.lower(City.name) == name.strip().lower(), City.country_id == country_id)
        return await self._session.scalar(stmt)

    async def find_unique_city_id(self, text: str) -> int | None:
        """The id of the one city (in any country) named `text`, case-insensitive; None for no match or several."""
        stmt = select(City.id).where(func.lower(City.name) == text.strip().lower()).limit(2)
        ids = list((await self._session.scalars(stmt)).all())
        return ids[0] if len(ids) == 1 else None

    async def create_city(self, name: str, country_id: int) -> City:
        city = City(name=name.strip(), country_id=country_id)
        self._session.add(city)
        await self._session.flush()
        await self._session.refresh(city)
        return city

    async def update(self, city: City, changes: dict) -> None:
        for field, value in changes.items():
            setattr(city, field, value)
        await self._session.commit()
        await self._session.refresh(city)

    async def delete(self, city: City) -> None:
        await self._session.delete(city)
        await self._session.commit()

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, city: City) -> None:
        await self._session.refresh(city)

    async def rollback(self) -> None:
        await self._session.rollback()
