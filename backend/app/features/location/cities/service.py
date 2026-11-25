import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityCreate, CityFilters, CityRead, CityUpdate
from app.features.location.cities.tables import City
from app.features.location.countries.repository import CountryRepository
from app.features.location.countries.tables import Country
from app.features.location.default_tags import clean_tag_names
from app.features.location.errors import LocationConflictError, LocationNotFoundError
from app.features.location.hooks import LocationHooks

logger = logging.getLogger(__name__)


class CityResolver:
    """Find or create a country and a city from names, without committing: the caller owns the transaction."""

    def __init__(self, cities: CityRepository, countries: CountryRepository, hooks: LocationHooks):
        self._cities = cities
        self._countries = countries
        self._hooks = hooks

    async def resolve_country(self, name: str, code: str | None = None) -> Country:
        code = code.strip().upper() if code and code.strip() else None
        if code:
            by_code = await self._countries.get_country_by_code(code)
            if by_code is not None:
                return by_code
        by_name = await self._countries.get_country_by_name(name)
        if by_name is not None:
            if code and by_name.code is None:
                await self._countries.set_country_code(by_name, code)
            return by_name
        return await self._countries.create_country(name, code)

    async def resolve_city(self, name: str, country: Country) -> City:
        """The city named `name` in `country`, created (and the hooks told) when it does not exist."""
        found = await self._cities.get_city_in_country(name, country.id)
        if found is not None:
            return found
        city = await self._cities.create_city(name, country.id)
        await self._hooks.city_created(city)
        logger.info("City created: id=%d name=%r country_id=%d", city.id, city.name, country.id)
        return city


class CityService:
    def __init__(self, session: AsyncSession, hooks: LocationHooks):
        self._repo = CityRepository(session)
        self._country_repo = CountryRepository(session)
        self._resolver = CityResolver(self._repo, self._country_repo, hooks)
        self._hooks = hooks

    async def get_cities(self, filters: CityFilters) -> list[CityRead]:
        cities = await self._repo.get_cities(filters)
        logger.debug("Cities listed: count=%d", len(cities))
        return [CityRead.model_validate(c) for c in cities]

    async def get_city(self, city_id: int) -> CityRead | None:
        city = await self._repo.get_city(city_id)
        return CityRead.model_validate(city) if city else None

    async def create_city(self, data: CityCreate) -> CityRead:
        if data.country_id is not None:
            country = await self._country_repo.get_country(data.country_id)
            if country is None:
                raise LocationNotFoundError(f"Country {data.country_id} not found")
        else:
            country = await self._resolver.resolve_country(data.country or "", data.country_code)
        # Read the names now: a rollback expires the loaded country, and reading it afterwards fails in async code.
        taken = f"{data.name.strip()} already exists in {country.name}"
        if await self._repo.get_city_in_country(data.name, country.id) is not None:
            raise LocationConflictError(taken)
        try:
            city = await self._resolver.resolve_city(data.name, country)
            await self._repo.commit()
            await self._repo.refresh(city)
        except IntegrityError as exc:
            await self._repo.rollback()
            raise LocationConflictError(taken) from exc
        return CityRead.model_validate(city)

    async def update_city(self, city_id: int, data: CityUpdate) -> CityRead | None:
        city = await self._repo.get_city(city_id)
        if city is None:
            return None
        sent = data.model_dump(exclude_unset=True)
        changes = {k: v for k, v in sent.items() if v is not None and k != "default_tag_names"}
        target_country = changes.get("country_id", city.country_id)
        if "country_id" in changes and await self._country_repo.get_country(target_country) is None:
            raise LocationNotFoundError(f"Country {target_country} not found")
        name = changes.get("name", city.name)
        existing = await self._repo.get_city_in_country(name, target_country)
        if existing is not None and existing.id != city_id:
            raise LocationConflictError(f"{name.strip()} already exists in that country")
        if "name" in changes:
            changes["name"] = changes["name"].strip()
        if "default_tag_names" in sent:
            changes["default_tag_names"] = clean_tag_names(sent["default_tag_names"])
        await self._repo.update(city, changes)
        logger.info("City updated: id=%d fields=%s", city_id, list(changes.keys()))
        return CityRead.model_validate(city)

    async def delete_city(self, city_id: int) -> bool:
        city = await self._repo.get_city(city_id)
        if city is None:
            return False
        reason = await self._hooks.city_in_use(city)
        if reason:
            raise LocationConflictError(reason)
        after_delete = await self._hooks.before_delete(city_id=city_id)
        try:
            await self._repo.delete(city)
        except IntegrityError as exc:
            await self._repo.rollback()
            raise LocationConflictError("The city is still in use") from exc
        logger.info("City deleted: id=%d", city_id)
        await after_delete()
        return True
