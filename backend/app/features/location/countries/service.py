import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.countries.repository import CountryRepository
from app.features.location.countries.schemas import CountryRead, CountryRef, CountryUpdate
from app.features.location.default_tags import clean_tag_names
from app.features.location.errors import LocationConflictError
from app.features.location.hooks import LocationHooks

logger = logging.getLogger(__name__)


class CountryService:
    def __init__(self, session: AsyncSession, hooks: LocationHooks):
        self._repo = CountryRepository(session)
        self._hooks = hooks

    async def get_countries(self) -> list[CountryRef]:
        return [CountryRef.model_validate(c) for c in await self._repo.get_countries()]

    async def get_country(self, country_id: int) -> CountryRead | None:
        country = await self._repo.get_country(country_id)
        return CountryRead.model_validate(country) if country else None

    async def update_country(self, country_id: int, data: CountryUpdate) -> CountryRead | None:
        country = await self._repo.get_country(country_id)
        if country is None:
            return None
        changes = data.model_dump(exclude_unset=True)
        if changes.get("name") is None:
            changes.pop("name", None)
        else:
            changes["name"] = changes["name"].strip()
            other = await self._repo.get_country_by_name(changes["name"])
            if other is not None and other.id != country_id:
                raise LocationConflictError(f"{changes['name']} already exists")
        if changes.get("code") and await self._repo.get_other_country_by_code(changes["code"], country_id) is not None:
            raise LocationConflictError(f"Code {changes['code']} belongs to another country")
        if "default_tag_names" in changes:
            changes["default_tag_names"] = clean_tag_names(changes["default_tag_names"])
        await self._repo.update(country, changes)
        logger.info("Country updated: id=%d fields=%s", country_id, list(changes.keys()))
        return CountryRead.model_validate(country)

    async def delete_country(self, country_id: int) -> bool:
        country = await self._repo.get_country(country_id)
        if country is None:
            return False
        cities = await self._repo.count_cities(country_id)
        if cities:
            raise LocationConflictError(f"{country.name} still has {cities} city(ies)")
        after_delete = await self._hooks.before_delete(country_id=country_id)
        await self._repo.delete(country)
        logger.info("Country deleted: id=%d", country_id)
        await after_delete()
        return True
