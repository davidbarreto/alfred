from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.location.countries.tables import Country


class CountryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_country(self, country_id: int) -> Country | None:
        return await self._session.get(Country, country_id)

    async def get_countries(self) -> list[Country]:
        stmt = select(Country).order_by(func.lower(Country.name), Country.id)
        return list((await self._session.scalars(stmt)).all())

    async def get_country_by_code(self, code: str) -> Country | None:
        return await self._session.scalar(select(Country).where(Country.code == code))

    async def get_country_by_name(self, name: str) -> Country | None:
        return await self._session.scalar(select(Country).where(func.lower(Country.name) == name.strip().lower()))

    async def get_other_country_by_code(self, code: str, country_id: int) -> Country | None:
        return await self._session.scalar(select(Country).where(Country.code == code, Country.id != country_id))

    async def count_cities(self, country_id: int) -> int:
        stmt = select(func.count()).select_from(City).where(City.country_id == country_id)
        return int(await self._session.scalar(stmt) or 0)

    async def create_country(self, name: str, code: str | None) -> Country:
        country = Country(name=name.strip(), code=code)
        self._session.add(country)
        await self._session.flush()
        return country

    async def set_country_code(self, country: Country, code: str) -> None:
        country.code = code
        await self._session.flush()

    async def update(self, country: Country, changes: dict) -> None:
        for field, value in changes.items():
            setattr(country, field, value)
        await self._session.commit()
        await self._session.refresh(country)

    async def delete(self, country: Country) -> None:
        await self._session.delete(country)
        await self._session.commit()
