import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.notes_index import WEB_LINK_NOTE, TravelNoteIndex
from app.features.location.cities.repository import CityRepository
from app.features.location.countries.repository import CountryRepository
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.links.kind import display_domain, guess_kind, is_social
from app.features.travel.links.repository import WebLinkRepository
from app.features.travel.links.schemas import WebLinkCreate, WebLinkRead, WebLinkUpdate
from app.features.travel.links.tables import WebLink
from app.integrations.link_preview.client import LinkPreview, LinkPreviewClient

logger = logging.getLogger(__name__)


class WebLinkService:
    def __init__(
        self, session: AsyncSession, preview_client: LinkPreviewClient, embedding_service: EmbeddingService | None = None
    ):
        self._session = session
        self._repo = WebLinkRepository(session)
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)
        self._city_repo = CityRepository(session)
        self._country_repo = CountryRepository(session)
        self._preview = preview_client
        self._notes = TravelNoteIndex(embedding_service)

    async def _trip_name(self, trip_id: int) -> str:
        trip = await self._trip_repo.get_trip(trip_id)
        if trip is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        return trip.name

    async def _place_name(self, place_id: int) -> str:
        place = await self._place_repo.get_place(place_id)
        if place is None:
            raise TravelNotFoundError(f"Place {place_id} not found")
        return place.name

    async def _city_name(self, city_id: int) -> str:
        city = await self._city_repo.get_city(city_id)
        if city is None:
            raise TravelNotFoundError(f"City {city_id} not found")
        return city.name

    async def _country_name(self, country_id: int) -> str:
        country = await self._country_repo.get_country(country_id)
        if country is None:
            raise TravelNotFoundError(f"Country {country_id} not found")
        return country.name

    async def _preview_for(self, url: str, kind: str) -> LinkPreview:
        """Social platforms answer scrapers with a login wall, so they are saved without a fetch."""
        if is_social(kind):
            return LinkPreview()
        return await self._preview.fetch(url) or LinkPreview()

    async def _label(self, link: WebLink) -> str:
        if link.trip_id:
            parent = await self._trip_name(link.trip_id)
        elif link.place_id:
            parent = await self._place_name(link.place_id)
        elif link.city_id:
            parent = await self._city_name(link.city_id)
        else:
            parent = await self._country_name(link.country_id)
        return f"Link for {parent} ({link.title or display_domain(link.url)})"

    async def _sync_notes(self, link: WebLink) -> None:
        await self._notes.sync(WEB_LINK_NOTE, link.id, await self._label(link), link.notes)

    async def get_trip_links(self, trip_id: int) -> list[WebLinkRead]:
        await self._trip_name(trip_id)
        return [WebLinkRead.model_validate(link) for link in await self._repo.get_links(trip_id=trip_id)]

    async def get_place_links(self, place_id: int) -> list[WebLinkRead]:
        await self._place_name(place_id)
        return [WebLinkRead.model_validate(link) for link in await self._repo.get_links(place_id=place_id)]

    async def get_city_links(self, city_id: int) -> list[WebLinkRead]:
        await self._city_name(city_id)
        return [WebLinkRead.model_validate(link) for link in await self._repo.get_links(city_id=city_id)]

    async def get_country_links(self, country_id: int) -> list[WebLinkRead]:
        await self._country_name(country_id)
        return [WebLinkRead.model_validate(link) for link in await self._repo.get_links(country_id=country_id)]

    async def get_link(self, link_id: int) -> WebLinkRead | None:
        link = await self._repo.get_link(link_id)
        return WebLinkRead.model_validate(link) if link else None

    async def _create(self, parent: dict[str, int], data: WebLinkCreate) -> WebLinkRead:
        kind = data.kind or guess_kind(data.url)
        preview = await self._preview_for(data.url, kind)
        try:
            link = await self._repo.create_link({
                **parent, "url": data.url, "kind": kind, "title": data.title or preview.title,
                "description": preview.description, "image_url": preview.image_url, "notes": data.notes,
            })
        except IntegrityError as exc:
            await self._session.rollback()
            raise TravelConflictError("This link is already saved here") from exc
        logger.info("Web link created: id=%d kind=%s host=%s", link.id, link.kind, display_domain(link.url))
        await self._sync_notes(link)
        return WebLinkRead.model_validate(link)

    async def create_trip_link(self, trip_id: int, data: WebLinkCreate) -> WebLinkRead:
        await self._trip_name(trip_id)
        return await self._create({"trip_id": trip_id}, data)

    async def create_place_link(self, place_id: int, data: WebLinkCreate) -> WebLinkRead:
        await self._place_name(place_id)
        return await self._create({"place_id": place_id}, data)

    async def create_city_link(self, city_id: int, data: WebLinkCreate) -> WebLinkRead:
        await self._city_name(city_id)
        return await self._create({"city_id": city_id}, data)

    async def create_country_link(self, country_id: int, data: WebLinkCreate) -> WebLinkRead:
        await self._country_name(country_id)
        return await self._create({"country_id": country_id}, data)

    async def update_link(self, link_id: int, data: WebLinkUpdate) -> WebLinkRead | None:
        current = await self._repo.get_link(link_id)
        if current is None:
            logger.debug("Web link update: id=%d not found", link_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        for required in ("url", "kind"):
            if required in changes and changes[required] is None:
                raise ValueError(f"{required} cannot be null")
        if "url" in changes and changes["url"] != current.url:
            # A different page: its title, description and image are no longer the old page's.
            changes.setdefault("kind", guess_kind(changes["url"]))
            preview = await self._preview_for(changes["url"], changes["kind"])
            changes.update(description=preview.description, image_url=preview.image_url)
            changes.setdefault("title", preview.title)
        try:
            link = await self._repo.update_link(link_id, changes)
        except IntegrityError as exc:
            await self._session.rollback()
            raise TravelConflictError("This link is already saved here") from exc
        logger.info("Web link updated: id=%d fields=%s", link_id, list(changes.keys()))
        await self._sync_notes(link)
        return WebLinkRead.model_validate(link)

    async def delete_link(self, link_id: int) -> bool:
        deleted = await self._repo.delete_link(link_id)
        if deleted:
            logger.info("Web link deleted: id=%d", link_id)
            await self._notes.remove(WEB_LINK_NOTE, link_id)
        return deleted
