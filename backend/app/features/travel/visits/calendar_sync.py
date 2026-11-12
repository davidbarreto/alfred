"""Google Calendar events for timed visits. A failure here never fails the visit write: it is logged and skipped."""
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.calendar_events.schemas import EventCreate, EventRead, EventUpdate
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.travel.default_tags import parse_default_tag_names
from app.features.travel.links import place_maps_url
from app.features.travel.settings_service import DEFAULT_VISIT_DURATION_MIN as DEFAULT_DURATION_MIN
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.visits.tables import Visit
from app.shared.timezone import local_timezone_name

logger = logging.getLogger(__name__)


DURATION_KEY = "travel.visit_duration_min"
EVENT_PROFILE = "normal"


def event_location(visit: Visit) -> str | None:
    place = visit.place
    return place.address or " ".join(p for p in (place.name, place.city) if p) or None


def event_description(visit: Visit) -> str | None:
    place = visit.place
    parts = [place_maps_url(place.name, place.city, place.maps_url, place.lat, place.lng), visit.notes]
    return "\n\n".join(p for p in parts if p) or None


def is_touchable(event: EventRead) -> bool:
    """A recurring event, one with guests or an all-day one is never rewritten from a visit."""
    return not (event.recurrence_rule or event.invitees or event.all_day)


class VisitCalendarSync:
    def __init__(self, session: AsyncSession, events_factory: Callable[[], Awaitable[CalendarEventService]]):
        # Built on first use: most visit requests never touch the calendar, so they skip the OAuth token lookup.
        self._events_factory = events_factory
        self._events: CalendarEventService | None = None
        self._settings = SettingService(session)
        self._stays = StayRepository(session)
        self._trips = TripRepository(session)

    async def _calendar(self) -> CalendarEventService:
        if self._events is None:
            self._events = await self._events_factory()
        return self._events

    async def event_exists(self, event_id: int) -> bool:
        return await (await self._calendar()).get_event(event_id) is not None

    async def _zone(self, visit: Visit) -> str:
        """The zone of the stay covering the visit's day, else the local zone."""
        for stay in await self._stays.get_stays(visit.trip_id) if visit.trip_id else []:
            local_in = stay.check_in_at.astimezone(ZoneInfo(stay.timezone)).date()
            local_out = stay.check_out_at.astimezone(ZoneInfo(stay.timezone)).date()
            if local_in <= visit.visit_date <= local_out:
                return stay.timezone
        return local_timezone_name()

    async def _duration(self) -> timedelta:
        raw = await self._settings.get_value(DURATION_KEY)
        try:
            minutes = int(raw) if raw else DEFAULT_DURATION_MIN
        except ValueError:
            minutes = DEFAULT_DURATION_MIN
        return timedelta(minutes=max(minutes, 1))

    async def create_event(self, visit: Visit) -> int | None:
        """Create the event for a timed visit of a trip; the new event id, or None when it cannot be made."""
        if visit.visit_date is None or visit.visit_time is None or visit.trip_id is None:
            return None
        try:
            trip = await self._trips.get_trip(visit.trip_id)
            start = datetime.combine(visit.visit_date, visit.visit_time)
            event = await (await self._calendar()).create_event(EventCreate(
                title=visit.place.name, description=event_description(visit), location=event_location(visit),
                start_datetime=start, end_datetime=start + await self._duration(), timezone=await self._zone(visit),
                tags=parse_default_tag_names(trip.default_tag_names if trip else None),
                notification_profile=EVENT_PROFILE,
            ))
        except Exception as exc:  # Google not authorized, API down, ...: the visit is saved regardless
            logger.warning("Visit event not created: visit_id=%d error=%s", visit.id, exc)
            return None
        logger.info("Visit event created: visit_id=%d event_id=%d", visit.id, event.id)
        return event.id

    async def update_event(self, visit: Visit) -> bool:
        """Move a linked event to the visit's day, time and place (start/end and location only); False when left alone."""
        if visit.calendar_event_id is None or visit.visit_date is None or visit.visit_time is None:
            return False
        try:
            calendar = await self._calendar()
            event = await calendar.get_event(visit.calendar_event_id)
            if event is None or not is_touchable(event):
                logger.info("Visit event left alone: visit_id=%d event_id=%s", visit.id, visit.calendar_event_id)
                return False
            zone = event.timezone or local_timezone_name()
            length = event.end_datetime - event.start_datetime
            start = datetime.combine(visit.visit_date, visit.visit_time)
            await calendar.update_event(event.id, EventUpdate(
                start_datetime=start, end_datetime=start + length, location=event_location(visit), timezone=zone,
            ))
        except Exception as exc:
            logger.warning("Visit event not updated: visit_id=%d error=%s", visit.id, exc)
            return False
        logger.info("Visit event updated: visit_id=%d event_id=%d", visit.id, visit.calendar_event_id)
        return True

    async def delete_event(self, event_id: int) -> bool:
        try:
            await (await self._calendar()).delete_event(event_id)
        except Exception as exc:
            logger.warning("Visit event not deleted: event_id=%d error=%s", event_id, exc)
            return False
        logger.info("Visit event deleted: event_id=%d", event_id)
        return True
