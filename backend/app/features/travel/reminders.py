"""Travel reminder candidates. Pure rules in `build_travel_reminders`; `TravelReminderService` loads the data.

The reminder scheduler (core/reminders) owns dedup and delivery: it asks for candidates and skips the ones
it already sent."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.recap.builder import build_recap
from app.features.travel.settings_schemas import TravelSettingsRead
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.service import TripService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

# Days before the first day of a trip on which a "trip starts" reminder is sent.
TRIP_START_REMINDER_DAYS = (7, 3, 1)
# Online check-in typically opens this long before a flight.
CHECK_IN_OPENS_BEFORE = timedelta(hours=24)
# The scheduler runs hourly: announce "time to leave" this long ahead of the leave-home time.
LEAVE_HOME_LEAD = timedelta(hours=1)
# Trips starting further away than this are not loaded for reminders.
LOOKAHEAD_DAYS = max(TRIP_START_REMINDER_DAYS)
# Days after a trip ends on which to nudge about the places still to grade or write down.
GRADE_NUDGE_DAYS = (1, 7)
# Trips that ended up to this long ago are loaded too, for the nudge.
LOOKBEHIND_DAYS = max(GRADE_NUDGE_DAYS)


@dataclass(frozen=True)
class TravelReminder:
    kind: str
    entity_id: int
    text: str
    # A reminder whose window can span midnight must be deduplicated over this many days.
    dedup_days: int = 1


def _at(instant: datetime, zone: str) -> str:
    return instant.astimezone(ZoneInfo(zone)).strftime("%H:%M")


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def build_travel_reminders(
    trips: list[TripDetail], now: datetime, today: date, settings: TravelSettingsRead
) -> list[TravelReminder]:
    reminders: list[TravelReminder] = []
    leave_minutes = settings.airport_buffer_min + settings.home_to_airport_min
    for trip in trips:
        days_until = (trip.start_date - today).days
        if days_until in TRIP_START_REMINDER_DAYS:
            text = f"Trip '{trip.name}' starts in {_plural(days_until, 'day')}"
            if trip.checklist_note_id:
                text += f" (checklist: note #{trip.checklist_note_id})"
            reminders.append(TravelReminder("travel_trip_start", trip.id, text))

        if (today - trip.end_date).days in GRADE_NUDGE_DAYS:
            pending = len(build_recap(trip, None).to_complete)
            if pending:
                reminders.append(TravelReminder(
                    "travel_grade_nudge", trip.id,
                    f"Trip '{trip.name}': {_plural(pending, 'place')} still to grade or note (recap: /travel/{trip.id}/recap)",
                ))

        flights = [leg for leg in trip.legs if leg.mode == "flight"]
        for leg in flights:
            if leg.departs_at - CHECK_IN_OPENS_BEFORE <= now < leg.departs_at:
                ident = " ".join(p for p in (leg.carrier, leg.number) if p) or f"{leg.origin} → {leg.destination}"
                reminders.append(TravelReminder(
                    "travel_check_in", leg.id,
                    f"Online check-in should be open for {ident} (departs {_at(leg.departs_at, leg.departs_tz)})",
                    dedup_days=2,
                ))

        # Home is where the trip starts: only the first leg, and only a flight, needs a leave-home time.
        first_leg = min(trip.legs, key=lambda leg: leg.departs_at, default=None)
        if first_leg is not None and first_leg.mode == "flight":
            leave_at = first_leg.departs_at - timedelta(minutes=leave_minutes)
            if leave_at - LEAVE_HOME_LEAD <= now < first_leg.departs_at:
                reminders.append(TravelReminder(
                    "travel_leave_home", first_leg.id,
                    f"Time to leave for the airport by {_at(leave_at, first_leg.departs_tz)} "
                    f"({first_leg.origin} → {first_leg.destination} departs {_at(first_leg.departs_at, first_leg.departs_tz)})",
                    dedup_days=2,
                ))

        for stay in trip.stays:
            local_now_at_stay = now.astimezone(ZoneInfo(stay.timezone))
            if local_now_at_stay.date() == stay.check_out_local.date() and now < stay.check_out_at:
                reminders.append(TravelReminder(
                    "travel_check_out", stay.id,
                    f"Check out today from {stay.place.name} at {stay.check_out_local:%H:%M}",
                ))
    return reminders


class TravelReminderService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = TripRepository(session)
        self._trips = TripService(session)
        self._settings = self._trips.settings_service

    async def get_reminders(self) -> list[TravelReminder]:
        now = local_now()
        today = now.date()
        trips = await self._repo.get_trips_in_window(today - timedelta(days=LOOKBEHIND_DAYS), today + timedelta(days=LOOKAHEAD_DAYS))
        details = [d for d in [await self._trips.get_trip_detail(t.id) for t in trips] if d is not None]
        reminders = build_travel_reminders(details, now, today, await self._settings.get())
        logger.debug("Travel reminders: trips=%d candidates=%d", len(details), len(reminders))
        return reminders
