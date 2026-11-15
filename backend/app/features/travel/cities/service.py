import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.cities.repository import CityRepository
from app.features.travel.cities.schemas import CityCreate, CityFilters, CityRead, CountryRef
from app.features.travel.cities.tables import City, Country
from app.features.travel.errors import TravelConflictError, TravelNotFoundError

logger = logging.getLogger(__name__)


class CityResolver:
    """Find or create a country and a city from names, without committing: the caller owns the transaction."""

    def __init__(self, repo: CityRepository):
        self._repo = repo

    async def resolve_country(self, name: str, code: str | None = None) -> Country:
        code = code.strip().upper() if code and code.strip() else None
        if code:
            by_code = await self._repo.get_country_by_code(code)
            if by_code is not None:
                return by_code
        by_name = await self._repo.get_country_by_name(name)
        if by_name is not None:
            if code and by_name.code is None:
                await self._repo.set_country_code(by_name, code)
            return by_name
        return await self._repo.create_country(name, code)

    async def resolve_city(self, name: str, country: Country) -> City:
        """The city named `name` in `country`, created (and its leg ends attached) when it does not exist."""
        found = await self._repo.get_city_in_country(name, country.id)
        if found is not None:
            return found
        city = await self._repo.create_city(name, country.id)
        attached = await self._repo.attach_leg_ends(city)
        logger.info("City created: id=%d name=%r country_id=%d leg_ends=%d", city.id, city.name, country.id, attached)
        return city


class CityService:
    def __init__(self, session: AsyncSession):
        self._repo = CityRepository(session)
        self._resolver = CityResolver(self._repo)

    async def get_countries(self) -> list[CountryRef]:
        return [CountryRef.model_validate(c) for c in await self._repo.get_countries()]

    async def get_cities(self, filters: CityFilters) -> list[CityRead]:
        cities = await self._repo.get_cities(filters)
        logger.debug("Cities listed: count=%d", len(cities))
        return [CityRead.model_validate(c) for c in cities]

    async def create_city(self, data: CityCreate) -> CityRead:
        if data.country_id is not None:
            country = await self._repo.get_country(data.country_id)
            if country is None:
                raise TravelNotFoundError(f"Country {data.country_id} not found")
        else:
            country = await self._resolver.resolve_country(data.country or "", data.country_code)
        # Read the names now: a rollback expires the loaded country, and reading it afterwards fails in async code.
        taken = f"{data.name.strip()} already exists in {country.name}"
        if await self._repo.get_city_in_country(data.name, country.id) is not None:
            raise TravelConflictError(taken)
        try:
            city = await self._resolver.resolve_city(data.name, country)
            await self._repo.commit()
            await self._repo.refresh(city)
        except IntegrityError as exc:
            await self._repo.rollback()
            raise TravelConflictError(taken) from exc
        return CityRead.model_validate(city)
