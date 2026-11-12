"""Rules for linking a calendar event to a leg, stay or visit: it must exist and belong to at most one item."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.travel.errors import TravelConflictError, TravelNotFoundError
from app.features.travel.legs.repository import LegRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.visits.repository import VisitRepository


class EventLinkChecker:
    def __init__(self, session: AsyncSession):
        self._events = CalendarEventRepository(session)
        self._legs = LegRepository(session)
        self._stays = StayRepository(session)
        self._visits = VisitRepository(session)

    async def ensure_free(self, event_id: int, own_kind: str | None = None, own_id: int | None = None) -> None:
        """Raise when the event is missing (404) or linked to another item (409); `own_*` is the item being edited."""
        if await self._events.get_event(event_id) is None:
            raise TravelNotFoundError(f"Calendar event {event_id} not found")
        holders = {
            "leg": await self._legs.get_leg_by_calendar_event(event_id),
            "stay": await self._stays.get_stay_by_calendar_event(event_id),
            "visit": await self._visits.get_visit_by_calendar_event(event_id),
        }
        for kind, holder in holders.items():
            if holder is not None and not (kind == own_kind and holder.id == own_id):
                raise TravelConflictError(f"Calendar event {event_id} is already linked to a {kind}")
