"""What a new city gets without anyone asking: coordinates for its map marker, its country's ISO code when missing,
and a cover photo. Runs in the background after a city is created (a failure leaves the city as it is) and from the
one-off backfill (`scripts/backfill_city_covers.py`)."""
import asyncio
import logging
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.repository import CityRepository
from app.features.location.cities.tables import City
from app.features.location.countries.repository import CountryRepository
from app.features.location.covers import CoverService, cover_titles
from app.shared.protocols.audio import FileStorage
from app.shared.protocols.media import CityGeocoder, CoverPhotoProvider, ImageFetcher

logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task] = set()
# The creating request commits after the hook runs: look for the city a few times before giving up.
_LOOKUP_DELAYS_SECONDS = (0.5, 1.0, 2.0)


class CityEnricher:
    def __init__(
        self, geocoder: CityGeocoder, photos: CoverPhotoProvider, images: ImageFetcher, storage: FileStorage,
        session_factory: Callable[[], AsyncSession] | None = None,
    ):
        self._geocoder = geocoder
        self._photos = photos
        self._images = images
        self._storage = storage
        self._session_factory = session_factory

    async def enrich(self, session: AsyncSession, city: City, covers: bool = True) -> list[str]:
        """Fill what the city and its country lack; returns what was filled ("coordinates", "country code", "cover")."""
        filled: list[str] = []
        cities, countries = CityRepository(session), CountryRepository(session)
        country = city.country
        if city.latitude is None or country.code is None:
            found = await self._geocoder.geocode(city.name, country.name, country.code, session=session)
            if found is not None:
                if city.latitude is None:
                    await cities.update(city, {"latitude": found.latitude, "longitude": found.longitude})
                    filled.append("coordinates")
                code = found.country_code
                if country.code is None and code and await countries.get_other_country_by_code(code, country.id) is None:
                    await countries.update(country, {"code": code})
                    filled.append("country code")
        if covers and city.cover_path is None:
            photo = await self._photos.find(cover_titles(city.name, country.name), session=session)
            if photo is not None:
                await CoverService(session, self._storage, self._photos, self._images).apply_city_photo(city, photo)
                filled.append("cover")
        # The provider-call log rows are still pending when nothing was filled.
        await cities.commit()
        if filled:
            logger.info("City enriched: id=%d filled=%s", city.id, filled)
        return filled

    def schedule(self, city_id: int) -> None:
        """Enrich the city once its creating transaction has committed, without making the caller wait."""
        if self._session_factory is None:
            return
        task = asyncio.create_task(self._enrich_later(city_id))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    async def _enrich_later(self, city_id: int) -> None:
        try:
            for delay in _LOOKUP_DELAYS_SECONDS:
                await asyncio.sleep(delay)
                async with self._session_factory() as session:
                    city = await CityRepository(session).get_city(city_id)
                    if city is not None:
                        await self.enrich(session, city)
                        return
            logger.warning("City enrichment skipped: id=%d not found", city_id)
        except Exception as exc:  # a background task has nobody to raise to
            logger.error("City enrichment failed: id=%d error=%s", city_id, exc)
