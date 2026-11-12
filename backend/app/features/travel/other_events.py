"""Calendar events that are not part of a trip: listed on the trip page and snoozed while the trip lasts.

Rules (`is_trip_event`, `trips_on`) are pure; `TripSnoozeService` loads the data. A trip event is one linked to a
leg, stay or visit, or tagged with one of the trip's default tags (case-insensitive)."""
import logging
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.schemas import EventFilters, EventRead
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.travel.default_tags import parse_default_tag_names
from app.features.travel.legs.repository import LegRepository
from app.features.travel.settings_service import TravelSettingsService
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.visits.repository import VisitRepository
from app.shared.timezone import local_naive_now

logger = logging.getLogger(__name__)

_MAX_EVENTS = 500


@dataclass(frozen=True)
class TripSpan:
    start: date
    end: date
    tags: frozenset[str]


class OtherEvent(BaseModel):
    event_id: int
    title: str
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool
    recurring: bool
    snoozed: bool


def span_of(trip) -> TripSpan:
    return TripSpan(trip.start_date, trip.end_date, frozenset(n.lower() for n in parse_default_tag_names(trip.default_tag_names)))


def trips_on(day: date, spans: list[TripSpan]) -> list[TripSpan]:
    return [s for s in spans if s.start <= day <= s.end]


def is_trip_event(event: EventRead, linked_ids: set[int], covering: list[TripSpan]) -> bool:
    if event.id in linked_ids:
        return True
    tags = {t.lower() for t in event.tags}
    return any(tags & span.tags for span in covering)


def snoozed_keys(events: list[EventRead], linked_ids: set[int], spans: list[TripSpan]) -> set[tuple[int, datetime]]:
    """(event id, occurrence start) of the events that fall on a trip day and are not part of the trip."""
    result: set[tuple[int, datetime]] = set()
    for event in events:
        covering = trips_on(event.start_datetime.date(), spans)
        if covering and not is_trip_event(event, linked_ids, covering):
            result.add((event.id, event.start_datetime))
    return result


class TripSnoozeService:
    def __init__(self, session: AsyncSession, events: CalendarEventService):
        self._events = events
        self._settings = TravelSettingsService(session)
        self._trips = TripRepository(session)
        self._legs = LegRepository(session)
        self._stays = StayRepository(session)
        self._visits = VisitRepository(session)

    async def _linked_ids(self, events: list[EventRead]) -> set[int]:
        ids = [e.id for e in events]
        found: set[int] = set()
        for repo in (self._legs, self._stays, self._visits):
            found |= set(await repo.get_imported_event_ids(ids))
        return found

    async def snoozed_for_digest(self, events: list[EventRead]) -> set[tuple[int, datetime]]:
        """Events whose reminders to hold back. Fails open: any error means nothing is snoozed."""
        try:
            if not events or not (await self._settings.get()).snooze_other_events:
                return set()
            days = [e.start_datetime.date() for e in events]
            trips = await self._trips.get_trips_overlapping(min(days), max(days))
            if not trips:
                return set()
            keys = snoozed_keys(events, await self._linked_ids(events), [span_of(t) for t in trips])
        except Exception as exc:
            logger.warning("Trip snooze skipped: error=%s", exc)
            return set()
        if keys:
            logger.info("Trip snooze: held back %d event reminder(s)", len(keys))
        return keys

    async def get_other_events(self, trip_id: int) -> list[OtherEvent] | None:
        """Events inside the trip's dates that are not part of it, with whether their reminders are snoozed."""
        trip = await self._trips.get_trip(trip_id)
        if trip is None:
            return None
        events = await self._events.get_events(EventFilters(
            limit=_MAX_EVENTS,
            start_from=datetime.combine(trip.start_date, datetime.min.time()),
            start_to=datetime.combine(trip.end_date, datetime.max.time()),
        ))
        spans = [span_of(trip)]
        linked = await self._linked_ids(events)
        enabled = (await self._settings.get()).snooze_other_events
        others = [e for e in events if not is_trip_event(e, linked, spans)]
        now = local_naive_now()
        return [
            OtherEvent(
                event_id=e.id, title=e.title, start_datetime=e.start_datetime, end_datetime=e.end_datetime,
                all_day=e.all_day, recurring=bool(e.recurrence_rule), snoozed=enabled and e.start_datetime >= now,
            )
            for e in others
        ]
