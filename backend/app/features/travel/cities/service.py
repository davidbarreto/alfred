import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.cities.repository import CityRepository
from app.features.travel.cities.schemas import (
    CityCreate, CityDetail, CityFilters, CityPlace, CityRead, CityUpdate, CountryCity, CountryDetail, CountryRef,
    CountryUpdate, LocationTrip,
)
from app.features.travel.cities.tables import City, Country
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.links.repository import WebLinkRepository
from app.features.travel.notes_index import WEB_LINK_NOTE, TravelNoteIndex
from app.features.travel.places.repository import PlaceRepository

_PLACES_SHOWN = 5


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None

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
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._repo = CityRepository(session)
        self._resolver = CityResolver(self._repo)
        self._place_repo = PlaceRepository(session)
        self._link_repo = WebLinkRepository(session)
        self._notes = TravelNoteIndex(embedding_service)

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

    async def _city_grades(self, city_ids: list[int]) -> tuple[dict[int, list[int]], dict[int, float]]:
        """Each city's place ids and the mean grade of its graded places (cities with no graded place are absent)."""
        place_ids = await self._repo.get_place_ids_by_city(city_ids)
        grades = await self._place_repo.get_grades([p for ids in place_ids.values() for p in ids])
        means = {}
        for city_id, ids in place_ids.items():
            mean = _mean([grades[p][0] for p in ids if p in grades])
            if mean is not None:
                means[city_id] = mean
        return place_ids, means

    async def get_city_detail(self, city_id: int) -> CityDetail | None:
        city = await self._repo.get_city(city_id)
        if city is None:
            return None
        place_ids, means = await self._city_grades([city_id])
        ids = place_ids[city_id]
        grades = await self._place_repo.get_grades(ids)
        places = [
            CityPlace(id=p.id, name=p.name, kind=p.kind, grade=grades[p.id][0] if p.id in grades else None)
            for p in await self._repo.get_places(ids, _PLACES_SHOWN)
        ]
        trips = [LocationTrip.model_validate(t) for t in await self._repo.get_trips_of_cities([city_id])]
        return CityDetail(
            **CityRead.model_validate(city).model_dump(), grade=means.get(city_id), grade_count=len(
                [p for p in ids if p in grades]
            ), place_count=len(ids), places=places, trips=trips,
        )

    async def get_country_detail(self, country_id: int) -> CountryDetail | None:
        country = await self._repo.get_country(country_id)
        if country is None:
            return None
        cities = await self._repo.get_country_cities(country_id)
        place_ids, means = await self._city_grades([c.id for c in cities])
        trips = [LocationTrip.model_validate(t) for t in await self._repo.get_trips_of_cities([c.id for c in cities])]
        return CountryDetail(
            **CountryRef.model_validate(country).model_dump(), created_at=country.created_at, updated_at=country.updated_at,
            grade=_mean(list(means.values())), grade_count=len(means),
            cities=[CountryCity(id=c.id, name=c.name, place_count=len(place_ids[c.id]), grade=means.get(c.id)) for c in cities],
            trips=trips,
        )

    async def update_city(self, city_id: int, data: CityUpdate) -> CityRead | None:
        city = await self._repo.get_city(city_id)
        if city is None:
            return None
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        target_country = changes.get("country_id", city.country_id)
        if "country_id" in changes and await self._repo.get_country(target_country) is None:
            raise TravelNotFoundError(f"Country {target_country} not found")
        name = changes.get("name", city.name)
        existing = await self._repo.get_city_in_country(name, target_country)
        if existing is not None and existing.id != city_id:
            raise TravelConflictError(f"{name.strip()} already exists in that country")
        if "name" in changes:
            changes["name"] = changes["name"].strip()
        await self._repo.update(city, changes)
        logger.info("City updated: id=%d fields=%s", city_id, list(changes.keys()))
        return CityRead.model_validate(city)

    async def update_country(self, country_id: int, data: CountryUpdate) -> CountryRef | None:
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
                raise TravelConflictError(f"{changes['name']} already exists")
        if changes.get("code") and await self._repo.get_other_country_by_code(changes["code"], country_id) is not None:
            raise TravelConflictError(f"Code {changes['code']} belongs to another country")
        await self._repo.update(country, changes)
        logger.info("Country updated: id=%d fields=%s", country_id, list(changes.keys()))
        return CountryRef.model_validate(country)

    async def delete_city(self, city_id: int) -> bool:
        city = await self._repo.get_city(city_id)
        if city is None:
            return False
        places, leg_ends = await self._repo.count_places(city_id), await self._repo.count_leg_ends(city_id)
        if places or leg_ends:
            raise TravelConflictError(f"{city.name} is used by {places} place(s) and {leg_ends} leg end(s)")
        link_ids = await self._link_repo.get_link_ids(city_id=city_id)
        try:
            await self._repo.delete(city)
        except IntegrityError as exc:
            await self._repo.rollback()
            raise TravelConflictError("The city is still in use") from exc
        logger.info("City deleted: id=%d", city_id)
        for link_id in link_ids:
            await self._notes.remove(WEB_LINK_NOTE, link_id)
        return True

    async def delete_country(self, country_id: int) -> bool:
        country = await self._repo.get_country(country_id)
        if country is None:
            return False
        cities = await self._repo.get_country_cities(country_id)
        if cities:
            raise TravelConflictError(f"{country.name} still has {len(cities)} city(ies)")
        link_ids = await self._link_repo.get_link_ids(country_id=country_id)
        await self._repo.delete(country)
        logger.info("Country deleted: id=%d", country_id)
        for link_id in link_ids:
            await self._notes.remove(WEB_LINK_NOTE, link_id)
        return True
