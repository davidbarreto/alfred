import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.notes_index import VISIT_NOTE, TravelNoteIndex
from app.features.travel.event_links import EventLinkChecker
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.visits.calendar_sync import VisitCalendarSync
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitCreate, VisitFilters, VisitMove, VisitMoveResult, VisitRead, VisitUpdate

logger = logging.getLogger(__name__)

_NOT_NULL = ("place_id", "status")


class VisitService:
    def __init__(
        self, session: AsyncSession, embedding_service: EmbeddingService | None = None,
        calendar: VisitCalendarSync | None = None,
    ):
        self._calendar = calendar
        self._event_links = EventLinkChecker(session)
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
            await self._event_links.ensure_free(data.calendar_event_id)
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
            await self._event_links.ensure_free(changes["calendar_event_id"], "visit", visit_id)
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

    async def event_action(self, visit_id: int, action: str) -> VisitRead | None:
        """Repair the link between a visit and its calendar event, in either direction.

        create: make the event for a visit that has none; update_event: push the visit's day, time and place to the
        event; update_visit: take the event's day and time. Raises ValueError with the reason when nothing changed."""
        visit = await self._repo.get_visit(visit_id)
        if visit is None:
            return None
        if self._calendar is None:
            raise ValueError("Calendar events are not available")
        if action == "create":
            if visit.calendar_event_id is not None:
                raise ValueError("The visit already has a calendar event")
            if visit.visit_date is None or visit.visit_time is None or visit.trip_id is None:
                raise ValueError("The visit needs a trip, a day and a time first")
            event_id = await self._calendar.create_event(visit)
            if event_id is None:
                raise ValueError("The event could not be created (is Google Calendar connected?)")
            visit = await self._repo.update_visit(visit, {"calendar_event_id": event_id})
        elif action == "update_event":
            if visit.calendar_event_id is None or not await self._calendar.update_event(visit):
                raise ValueError("The event was not changed (it is missing, recurring, has guests or is all-day)")
        elif action == "update_visit":
            start = await self._calendar.event_start(visit.calendar_event_id) if visit.calendar_event_id else None
            if start is None:
                raise ValueError("The event is missing or has no start time")
            visit = await self._repo.update_visit(visit, {"visit_date": start[0], "visit_time": start[1]})
        else:
            raise ValueError("action must be create, update_event or update_visit")
        logger.info("Visit event action: id=%d action=%s", visit_id, action)
        return VisitRead.model_validate(visit)

    async def move_visits(self, trip_id: int, data: VisitMove) -> VisitMoveResult:
        """Move planned visits of one day to another; each linked calendar event moves with its visit."""
        if await self._trip_repo.get_trip(trip_id) is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        tag = data.only_tag.strip().lower() if data.only_tag else None
        moved: list[int] = []
        failed: list[int] = []
        for visit in await self._repo.get_trip_visits(trip_id):
            if visit.status != "planned" or visit.visit_date != data.from_date:
                continue
            if data.visit_ids is not None and visit.id not in data.visit_ids:
                continue
            if tag and tag not in {t.name.lower() for t in visit.place.tags}:
                continue
            try:
                await self.update_visit(visit.id, VisitUpdate(visit_date=data.to_date))
                moved.append(visit.id)
            except Exception as exc:  # one bad visit must not stop the rest
                logger.warning("Visit move failed: id=%d error=%s", visit.id, exc)
                failed.append(visit.id)
        logger.info("Visits moved: trip_id=%d from=%s to=%s moved=%d failed=%d", trip_id, data.from_date, data.to_date, len(moved), len(failed))
        return VisitMoveResult(moved=moved, failed=failed)

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
