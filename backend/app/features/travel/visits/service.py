import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.notes_index import VISIT_NOTE, TravelNoteIndex
from app.features.travel.legs.repository import LegRepository
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.visits.calendar_sync import VisitCalendarSync
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitRead, VisitUpdate

logger = logging.getLogger(__name__)

_NOT_NULL = ("place_id", "status")


class VisitService:
    def __init__(
        self, session: AsyncSession, embedding_service: EmbeddingService | None = None,
        calendar: VisitCalendarSync | None = None,
    ):
        self._calendar = calendar
        self._leg_repo = LegRepository(session)
        self._stay_repo = StayRepository(session)
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

    async def _check_event_free(self, event_id: int, visit_id: int | None = None) -> None:
        """A calendar event belongs to at most one leg, stay or visit."""
        if self._calendar is not None and not await self._calendar.event_exists(event_id):
            raise TravelNotFoundError(f"Calendar event {event_id} not found")
        taken = await self._repo.get_visit_by_calendar_event(event_id)
        if (taken is not None and taken.id != visit_id) or await self._leg_repo.get_leg_by_calendar_event(event_id) \
                or await self._stay_repo.get_stay_by_calendar_event(event_id):
            raise TravelConflictError(f"Calendar event {event_id} is already linked to a leg, stay or visit")

    async def _create_event_if_due(self, visit) -> None:
        """A planned visit of a trip with a day and a time gets its own event (a failure only logs)."""
        if self._calendar is None or visit.calendar_event_id is not None or visit.status != "planned":
            return
        event_id = await self._calendar.create_event(visit)
        if event_id is not None:
            await self._repo.update_visit(visit, {"calendar_event_id": event_id})

    async def create_visit(self, data: VisitCreate) -> VisitRead:
        await self._check_refs(data.trip_id, data.place_id)
        if data.calendar_event_id is not None:
            await self._check_event_free(data.calendar_event_id)
        visit = await self._repo.create_visit(data.model_dump())
        await self._create_event_if_due(visit)
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
        if changes.get("calendar_event_id") is not None:
            await self._check_event_free(changes["calendar_event_id"], visit_id)
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
        if self._calendar is not None and changes.keys() & {"visit_date", "visit_time", "place_id", "trip_id"}:
            if visit.calendar_event_id is not None:
                await self._calendar.update_event(visit)
            else:
                await self._create_event_if_due(visit)
        return VisitRead.model_validate(visit)

    async def delete_visit(self, visit_id: int, delete_event: bool = False) -> bool:
        """Delete the visit; its linked calendar event is deleted too only when `delete_event` is true."""
        visit = await self._repo.get_visit(visit_id)
        if visit is None:
            return False
        event_id = visit.calendar_event_id
        await self._repo.delete_visit(visit)
        logger.info("Visit deleted: id=%d", visit_id)
        if delete_event and event_id is not None and self._calendar is not None:
            await self._calendar.delete_event(event_id)
        await self._notes.remove(VISIT_NOTE, visit_id)
        return True
