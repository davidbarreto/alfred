import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.notes_index import PLACE_NOTE, TravelNoteIndex
from app.features.travel.places.detail import PlaceDetail
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.places.schemas import PlaceCreate, PlaceFilters, PlaceLocations, PlaceRead, PlaceUpdate
from app.features.travel.places.tables import Place
from app.features.travel.stays.repository import StayRepository
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.repository import TravelTagRepository
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitRead

logger = logging.getLogger(__name__)


class PlaceInUseError(Exception):
    """The place has visits or stays, so it can't be deleted."""


class PlaceService:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._session = session
        self._notes = TravelNoteIndex(embedding_service)
        self._repo = PlaceRepository(session)
        self._tag_repo = TravelTagRepository(session)
        self._visit_repo = VisitRepository(session)
        self._stay_repo = StayRepository(session)

    async def _read_all(self, places: list[Place]) -> list[PlaceRead]:
        grades = await self._repo.get_grades([p.id for p in places])
        reads = []
        for place in places:
            grade, count = grades.get(place.id, (None, 0))
            reads.append(PlaceRead.model_validate(place).model_copy(update={"grade": grade, "grade_count": count}))
        return reads

    async def get_places(self, filters: PlaceFilters) -> list[PlaceRead]:
        places = await self._repo.get_places(filters)
        logger.debug("Places listed: count=%d", len(places))
        return await self._read_all(places)

    async def get_locations(self) -> PlaceLocations:
        cities, countries = await self._repo.get_locations()
        return PlaceLocations(cities=cities, countries=countries)

    async def get_place(self, place_id: int) -> PlaceRead | None:
        place = await self._repo.get_place(place_id)
        return (await self._read_all([place]))[0] if place else None

    async def get_place_detail(self, place_id: int) -> PlaceDetail | None:
        place = await self.get_place(place_id)
        if place is None:
            return None
        visits = [VisitRead.model_validate(v) for v in await self._visit_repo.get_place_visits(place_id)]
        stays = [StayRead.model_validate(s) for s in await self._stay_repo.get_place_stays(place_id)]
        return PlaceDetail(**place.model_dump(), visits=visits, stays=stays)

    async def create_place(self, data: PlaceCreate) -> PlaceRead:
        tags = await self._tag_repo.get_or_create_tags(data.tags)
        place = await self._repo.create_place(data.model_dump(exclude={"tags"}), tags)
        logger.info("Place created: id=%d kind=%s name=%r", place.id, place.kind, place.name)
        await self._notes.sync(PLACE_NOTE, place.id, place.name, place.notes)
        return (await self._read_all([place]))[0]

    async def update_place(self, place_id: int, data: PlaceUpdate) -> PlaceRead | None:
        changes = data.model_dump(exclude_unset=True, exclude={"tags"})
        for required in ("kind", "name"):
            if required in changes and changes[required] is None:
                raise ValueError(f"{required} cannot be null")
        tags = None
        if data.tags is not None:
            tags = await self._tag_repo.get_or_create_tags(data.tags)
        place = await self._repo.update_place(place_id, changes, tags)
        if place is None:
            logger.debug("Place update: id=%d not found", place_id)
            return None
        logger.info("Place updated: id=%d fields=%s", place_id, list(changes.keys()) + (["tags"] if tags is not None else []))
        if changes.keys() & {"notes", "name"}:
            await self._notes.sync(PLACE_NOTE, place.id, place.name, place.notes)
        return (await self._read_all([place]))[0]

    async def delete_place(self, place_id: int) -> bool:
        try:
            deleted = await self._repo.delete_place(place_id)
        except IntegrityError as exc:
            await self._session.rollback()
            raise PlaceInUseError(place_id) from exc
        if deleted:
            logger.info("Place deleted: id=%d", place_id)
            await self._notes.remove(PLACE_NOTE, place_id)
        return deleted
