import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.travel.calendar_import.schemas import CalendarCandidate
from app.features.travel.legs.repository import LegRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.repository import TripRepository
from app.shared.timezone import local_timezone, local_timezone_name

logger = logging.getLogger(__name__)

_MAX_EVENTS = 200


class CalendarImportService:
    """Lists events already in Alfred's local calendar copy; it never calls Google."""

    def __init__(self, session: AsyncSession):
        # No Google provider: this is a read of the local copy only.
        self._events = CalendarEventService(provider=None, session=session)
        self._trip_repo = TripRepository(session)
        self._leg_repo = LegRepository(session)
        self._stay_repo = StayRepository(session)

    async def get_candidates(self, trip_id: int) -> list[CalendarCandidate] | None:
        trip = await self._trip_repo.get_trip(trip_id)
        if trip is None:
            return None
        events = await self._events.get_events(EventFilters(
            limit=_MAX_EVENTS,
            start_from=datetime.combine(trip.start_date, time.min),
            start_to=datetime.combine(trip.end_date + timedelta(days=1), time.min),
        ))
        # A recurring event is a habit, not a booking.
        events = [e for e in events if not e.recurrence_rule]
        ids = [e.id for e in events]
        legs = await self._leg_repo.get_imported_event_ids(ids)
        stays = await self._stay_repo.get_imported_event_ids(ids)

        candidates = []
        for event in events:
            zone = event.timezone or local_timezone_name()
            candidate = CalendarCandidate(
                event_id=event.id, title=event.title, location=event.location, description=event.description,
                all_day=event.all_day, timezone=zone,
                start_local=self._in_zone(event.start_datetime, zone), end_local=self._in_zone(event.end_datetime, zone),
            )
            if event.id in legs:
                candidate.imported_as, candidate.imported_id = "leg", legs[event.id]
            elif event.id in stays:
                candidate.imported_as, candidate.imported_id = "stay", stays[event.id]
            candidates.append(candidate)
        logger.debug("Calendar import candidates: trip_id=%d count=%d", trip_id, len(candidates))
        return candidates

    @staticmethod
    def _in_zone(value: datetime, zone: str) -> datetime:
        """Events hold naive wall time in the portal's zone; show it as the wall time in the event's own zone."""
        aware = value.replace(tzinfo=local_timezone()) if value.tzinfo is None else value
        return aware.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
