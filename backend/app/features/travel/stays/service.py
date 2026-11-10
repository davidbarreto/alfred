import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.notes_index import STAY_NOTE, TravelNoteIndex
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.stays.schemas import StayCreate, StayRead, StayUpdate
from app.features.travel.trips.repository import TripRepository
from app.features.travel.zones import to_utc

logger = logging.getLogger(__name__)

_NOT_NULL = ("place_id", "check_in_at", "check_out_at", "timezone")


class StayService:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._notes = TravelNoteIndex(embedding_service)
        self._repo = StayRepository(session)
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)
        self._calendar_repo = CalendarEventRepository(session)

    async def get_stays(self, trip_id: int) -> list[StayRead]:
        stays = await self._repo.get_stays(trip_id)
        logger.debug("Stays listed: trip_id=%d count=%d", trip_id, len(stays))
        return [StayRead.model_validate(s) for s in stays]

    async def get_stay(self, stay_id: int) -> StayRead | None:
        stay = await self._repo.get_stay(stay_id)
        return StayRead.model_validate(stay) if stay else None

    async def _check_refs(self, trip_id: int | None, place_id: int | None) -> None:
        if trip_id is not None and await self._trip_repo.get_trip(trip_id) is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        if place_id is not None and await self._place_repo.get_place(place_id) is None:
            raise TravelNotFoundError(f"Place {place_id} not found")

    async def create_stay(self, data: StayCreate) -> StayRead:
        await self._check_refs(data.trip_id, data.place_id)
        if data.calendar_event_id is not None:
            if await self._calendar_repo.get_event(data.calendar_event_id) is None:
                raise TravelNotFoundError(f"Calendar event {data.calendar_event_id} not found")
            if await self._repo.get_stay_by_calendar_event(data.calendar_event_id) is not None:
                raise TravelConflictError("That calendar event is already imported as a stay")
        stay = await self._repo.create_stay(data.model_dump())
        logger.info("Stay created: id=%d trip_id=%s place_id=%d", stay.id, stay.trip_id, stay.place_id)
        await self._notes.sync(STAY_NOTE, stay.id, f"Stay at {stay.place.name}", stay.notes)
        return StayRead.model_validate(stay)

    async def update_stay(self, stay_id: int, data: StayUpdate) -> StayRead | None:
        stay = await self._repo.get_stay(stay_id)
        if stay is None:
            logger.debug("Stay update: id=%d not found", stay_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        for field in _NOT_NULL:
            if field in changes and changes[field] is None:
                raise ValueError(f"{field} cannot be null")
        await self._check_refs(changes.get("trip_id"), changes.get("place_id"))
        zone = changes.get("timezone", stay.timezone)
        for field in ("check_in_at", "check_out_at"):
            if field in changes:
                changes[field] = to_utc(changes[field], zone)
        if changes.get("check_out_at", stay.check_out_at) < changes.get("check_in_at", stay.check_in_at):
            raise ValueError("check_out_at cannot be before check_in_at")
        stay = await self._repo.update_stay(stay, changes)
        logger.info("Stay updated: id=%d fields=%s", stay_id, list(changes.keys()))
        if changes.keys() & {"notes", "place_id"}:
            await self._notes.sync(STAY_NOTE, stay.id, f"Stay at {stay.place.name}", stay.notes)
        return StayRead.model_validate(stay)

    async def delete_stay(self, stay_id: int) -> bool:
        stay = await self._repo.get_stay(stay_id)
        if stay is None:
            return False
        await self._repo.delete_stay(stay)
        logger.info("Stay deleted: id=%d", stay_id)
        await self._notes.remove(STAY_NOTE, stay_id)
        return True
