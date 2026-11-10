import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.notes_index import VISIT_NOTE, TravelNoteIndex
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitRead, VisitUpdate

logger = logging.getLogger(__name__)

_NOT_NULL = ("place_id", "status")


class VisitService:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._notes = TravelNoteIndex(embedding_service)
        self._repo = VisitRepository(session)
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)

    async def get_visits(self, filters: VisitFilters) -> list[VisitRead]:
        visits = await self._repo.get_visits(filters)
        logger.debug("Visits listed: count=%d", len(visits))
        return [VisitRead.model_validate(v) for v in visits]

    async def get_visit(self, visit_id: int) -> VisitRead | None:
        visit = await self._repo.get_visit(visit_id)
        return VisitRead.model_validate(visit) if visit else None

    async def _check_refs(self, trip_id: int | None, place_id: int | None) -> None:
        if trip_id is not None and await self._trip_repo.get_trip(trip_id) is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        if place_id is not None and await self._place_repo.get_place(place_id) is None:
            raise TravelNotFoundError(f"Place {place_id} not found")

    async def create_visit(self, data: VisitCreate) -> VisitRead:
        await self._check_refs(data.trip_id, data.place_id)
        visit = await self._repo.create_visit(data.model_dump())
        logger.info("Visit created: id=%d place_id=%d trip_id=%s status=%s", visit.id, visit.place_id, visit.trip_id, visit.status)
        await self._notes.sync(VISIT_NOTE, visit.id, f"Visit to {visit.place.name}", visit.notes)
        return VisitRead.model_validate(visit)

    async def update_visit(self, visit_id: int, data: VisitUpdate) -> VisitRead | None:
        visit = await self._repo.get_visit(visit_id)
        if visit is None:
            logger.debug("Visit update: id=%d not found", visit_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        for field in _NOT_NULL:
            if field in changes and changes[field] is None:
                raise ValueError(f"{field} cannot be null")
        await self._check_refs(changes.get("trip_id"), changes.get("place_id"))
        status = changes.get("status", visit.status)
        if status != "visited":
            # Moving a graded visit back to planned/missed drops the grade; sending both is a contradiction.
            if changes.get("grade") is not None:
                raise ValueError("Only a visited visit can be graded")
            if visit.grade is not None:
                changes["grade"] = None
        visit = await self._repo.update_visit(visit, changes)
        logger.info("Visit updated: id=%d fields=%s", visit_id, list(changes.keys()))
        if changes.keys() & {"notes", "place_id"}:
            await self._notes.sync(VISIT_NOTE, visit.id, f"Visit to {visit.place.name}", visit.notes)
        return VisitRead.model_validate(visit)

    async def delete_visit(self, visit_id: int) -> bool:
        visit = await self._repo.get_visit(visit_id)
        if visit is None:
            return False
        await self._repo.delete_visit(visit)
        logger.info("Visit deleted: id=%d", visit_id)
        await self._notes.remove(VISIT_NOTE, visit_id)
        return True
