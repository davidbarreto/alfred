import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.location.cities.tables import City
from app.features.location.hooks import AfterDelete
from app.features.location.places.repository import PlaceRepository
from app.features.travel.cities.repository import TravelCityRepository
from app.features.travel.cities.service import is_home_city
from app.features.travel.links.repository import WebLinkRepository
from app.features.travel.notes_index import WEB_LINK_NOTE, TravelNoteIndex
from app.features.travel.trips.repository import TripRepository

logger = logging.getLogger(__name__)


class TravelLocationHooks:
    """Travel's side of a city's or country's life (`location.hooks.LocationHooks`)."""

    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._repo = TravelCityRepository(session)
        self._trip_repo = TripRepository(session)
        self._link_repo = WebLinkRepository(session)
        self._places = PlaceRepository(session)
        self._notes = TravelNoteIndex(embedding_service)

    async def city_created(self, city: City) -> None:
        """Leg ends typed before the city existed get it."""
        attached = await self._repo.attach_leg_ends(city)
        if attached:
            logger.info("Leg ends attached to a new city: city_id=%d count=%d", city.id, attached)

    async def city_in_use(self, city: City) -> str | None:
        if await is_home_city(self._places, city.id):
            return f"{city.name} is the home city (the Home place is there)"
        places, leg_ends = await self._repo.count_places(city.id), await self._repo.count_leg_ends(city.id)
        home_trips = await self._trip_repo.count_home_city_trips(city.id)
        if places or leg_ends or home_trips:
            return f"{city.name} is used by {places} place(s), {leg_ends} leg end(s) and {home_trips} trip home(s)"
        return None

    async def before_delete(self, *, city_id: int | None = None, country_id: int | None = None) -> AfterDelete:
        """The links go with the city or country (CASCADE); their note embeddings are dropped after the commit."""
        link_ids = await self._link_repo.get_link_ids(city_id=city_id, country_id=country_id)

        async def _drop_link_notes() -> None:
            for link_id in link_ids:
                await self._notes.remove(WEB_LINK_NOTE, link_id)

        return _drop_link_notes
