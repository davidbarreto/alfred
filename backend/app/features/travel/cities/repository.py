from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.cities.schemas import CityFilters
from app.features.travel.cities.tables import City, Country
from app.features.travel.legs.tables import Leg


class CityRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_city(self, city_id: int) -> City | None:
        return await self._session.get(City, city_id)

    async def get_country(self, country_id: int) -> Country | None:
        return await self._session.get(Country, country_id)

    async def get_countries(self) -> list[Country]:
        stmt = select(Country).order_by(func.lower(Country.name), Country.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_cities(self, filters: CityFilters) -> list[City]:
        stmt = select(City)
        if filters.country_id is not None:
            stmt = stmt.where(City.country_id == filters.country_id)
        if filters.q and filters.q.strip():
            stmt = stmt.where(func.lower(City.name).like(f"%{filters.q.strip().lower()}%"))
        stmt = stmt.order_by(func.lower(City.name), City.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_country_by_code(self, code: str) -> Country | None:
        return await self._session.scalar(select(Country).where(Country.code == code))

    async def get_country_by_name(self, name: str) -> Country | None:
        return await self._session.scalar(select(Country).where(func.lower(Country.name) == name.strip().lower()))

    async def get_city_in_country(self, name: str, country_id: int) -> City | None:
        stmt = select(City).where(func.lower(City.name) == name.strip().lower(), City.country_id == country_id)
        return await self._session.scalar(stmt)

    async def find_unique_city_id(self, text: str) -> int | None:
        """The id of the one city (in any country) named `text`, case-insensitive; None for no match or several."""
        stmt = select(City.id).where(func.lower(City.name) == text.strip().lower()).limit(2)
        ids = list((await self._session.scalars(stmt)).all())
        return ids[0] if len(ids) == 1 else None

    async def create_country(self, name: str, code: str | None) -> Country:
        country = Country(name=name.strip(), code=code)
        self._session.add(country)
        await self._session.flush()
        return country

    async def set_country_code(self, country: Country, code: str) -> None:
        country.code = code
        await self._session.flush()

    async def create_city(self, name: str, country_id: int) -> City:
        city = City(name=name.strip(), country_id=country_id)
        self._session.add(city)
        await self._session.flush()
        await self._session.refresh(city)
        return city

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

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, city: City) -> None:
        await self._session.refresh(city)

    async def rollback(self) -> None:
        await self._session.rollback()
