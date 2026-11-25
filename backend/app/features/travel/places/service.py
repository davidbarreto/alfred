import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.features.core.embeddings.service import EmbeddingService
from app.features.location.cities.repository import CityRepository
from app.features.location.cities.service import CityResolver
from app.features.location.countries.repository import CountryRepository
from app.features.location.places.schemas import PlaceCreate, PlaceUpdate
from app.features.location.places.service import PlaceService
from app.features.location.places.tables import Place
from app.features.travel.cities.hooks import TravelLocationHooks
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.places.detail import TravelPlaceDetail
from app.features.travel.places.repository import TravelPlaceRepository
from app.features.travel.places.schemas import (
    PlaceLocations,
    TravelPlaceCreate,
    TravelPlaceFilters,
    TravelPlaceRead,
    TravelPlaceUpdate,
)
from app.features.travel.stays.repository import StayRepository
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.repository import TravelTagRepository
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitRead

logger = logging.getLogger(__name__)

_CITY_FORM = ("city", "country", "country_code")


class TravelPlaceService:
    """Travel's view of places (tags, derived grade, visits and stays), and creating or editing a place with its tags
    in one call. What a place is goes through location's `PlaceService`."""

    def __init__(self, session: AsyncSession, places: PlaceService, embedding_service: EmbeddingService | None = None):
        self._places = places
        self._repo = TravelPlaceRepository(session)
        self._city_repo = CityRepository(session)
        self._cities = CityResolver(self._city_repo, CountryRepository(session), TravelLocationHooks(session, embedding_service))
        self._tag_repo = TravelTagRepository(session)
        self._visit_repo = VisitRepository(session)
        self._stay_repo = StayRepository(session)

    async def _read_all(self, places: list[Place]) -> list[TravelPlaceRead]:
        grades = await self._repo.get_grades([p.id for p in places])
        reads = []
        for place in places:
            grade, count = grades.get(place.id, (None, 0))
            reads.append(TravelPlaceRead.model_validate(place).model_copy(update={"grade": grade, "grade_count": count}))
        return reads

    async def get_places(self, filters: TravelPlaceFilters) -> list[TravelPlaceRead]:
        places = await self._repo.get_places(filters)
        logger.debug("Travel places listed: count=%d", len(places))
        return await self._read_all(places)

    async def get_locations(self) -> PlaceLocations:
        cities, countries = await self._repo.get_locations()
        return PlaceLocations(cities=cities, countries=countries)

    async def get_place(self, place_id: int) -> TravelPlaceRead | None:
        place = await self._repo.get_place(place_id)
        return (await self._read_all([place]))[0] if place else None

    async def get_place_detail(self, place_id: int) -> TravelPlaceDetail | None:
        place = await self.get_place(place_id)
        if place is None:
            return None
        visits = [VisitRead.model_validate(v) for v in await self._visit_repo.get_place_visits(place_id)]
        stays = [StayRead.model_validate(s) for s in await self._stay_repo.get_place_stays(place_id)]
        return TravelPlaceDetail(**place.model_dump(exclude={"opening_hours_text", "maps_link"}), visits=visits, stays=stays)

    async def _city_id(self, city_id: int | None, city: str | None, country: str | None, code: str | None) -> int:
        """The id of the city a place form named, finding or creating it (and its country) by name."""
        if city_id is not None:
            if await self._city_repo.get_city(city_id) is None:
                raise TravelNotFoundError(f"City {city_id} not found")
            return city_id
        resolved = await self._cities.resolve_city(city or "", await self._cities.resolve_country(country or "", code))
        return resolved.id

    async def create_place(self, data: TravelPlaceCreate) -> TravelPlaceRead:
        fields = data.model_dump(exclude={"tags", *_CITY_FORM}, exclude_unset=True)
        fields["kind"] = data.kind
        fields["city_id"] = await self._city_id(data.city_id, data.city, data.country, data.country_code)
        place = await self._places.add(PlaceCreate(**fields))
        # A new place has no tags: mark the empty collection as loaded, so assigning it doesn't lazy-load (async IO).
        set_committed_value(place, "tags", [])
        place.tags = await self._tag_repo.get_or_create_tags(data.tags)
        await self._places.saved(place.id, created=True)
        return await self._require(place.id)

    async def update_place(self, place_id: int, data: TravelPlaceUpdate) -> TravelPlaceRead | None:
        changes = data.model_dump(exclude_unset=True, exclude={"tags", *_CITY_FORM})
        if data.city_id is None:
            changes.pop("city_id", None)
        current = await self._repo.get_place(place_id)
        if current is None:
            logger.debug("Travel place update: id=%d not found", place_id)
            return None
        if data.city_id is not None or data.city is not None or data.country is not None:
            changes["city_id"] = await self._city_id(
                data.city_id, data.city or current.city.name, data.country or current.city.country.name, data.country_code
            )
        if changes:
            await self._places.update(place_id, PlaceUpdate(**changes))
        if data.tags is not None:
            place = await self._repo.get_place(place_id)
            assert place is not None
            await self._repo.set_tags(place, await self._tag_repo.get_or_create_tags(data.tags))
            logger.info("Travel place tags set: id=%d count=%d", place_id, len(data.tags))
        return await self._require(place_id)

    async def _require(self, place_id: int) -> TravelPlaceRead:
        place = await self.get_place(place_id)
        assert place is not None
        return place
