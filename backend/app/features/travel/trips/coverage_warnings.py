"""Pure functions: warnings about gaps in a trip's lodging and about visits that cannot work. No DB or IO."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.features.travel.legs.schemas import LegRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.timeline import TripWarning, _same_place
from app.features.travel.visits.schemas import VisitRead
from app.features.travel.zones import to_utc

def _list_dates(days: list[date]) -> str:
    return ", ".join(f"{d:%d %b}" for d in days)


def find_lodging_warnings(legs: list[LegRead], stays: list[StayRead]) -> list[TripWarning]:
    """Nights between the first arrival and the last departure with no stay, and a trip that does not end where it began."""
    if not legs:
        return []
    ordered = sorted(legs, key=lambda leg: (leg.departs_at, leg.id))
    warnings: list[TripWarning] = []

    first_night = ordered[0].arrives_local.date()
    last_morning = ordered[-1].departs_local.date()
    uncovered: list[date] = []
    night = first_night
    while night < last_morning:
        in_transit = any(leg.departs_local.date() <= night < leg.arrives_local.date() for leg in ordered)
        covered = any(s.check_in_local.date() <= night < s.check_out_local.date() for s in stays)
        if not covered and not in_transit:
            uncovered.append(night)
        night += timedelta(days=1)
    if uncovered:
        count = len(uncovered)
        warnings.append(TripWarning(
            kind="uncovered_night",
            message=f"No stay for {count} night{'s' if count != 1 else ''}: {_list_dates(uncovered)}",
        ))

    first, last = ordered[0], ordered[-1]
    if len(ordered) > 1 and not (_same_place(last.destination, first.origin) or _same_place(first.origin, last.destination)):
        warnings.append(TripWarning(
            kind="no_return_leg", leg_id=last.id,
            message=f"The trip began in {first.origin} but the last leg ends in {last.destination}",
        ))
    return warnings


def _covering_stay(day: date, stays: list[StayRead]) -> StayRead | None:
    return next((s for s in stays if s.check_in_local.date() <= day <= s.check_out_local.date()), None)


def _visit_instant(visit: VisitRead, stays: list[StayRead], legs: list[LegRead]) -> datetime | None:
    """A timed visit as an instant, read in the zone of the stay covering that day (else of the latest arrival before it)."""
    if visit.visit_date is None or visit.visit_time is None:
        return None
    stay = _covering_stay(visit.visit_date, stays)
    zone = stay.timezone if stay else None
    if zone is None:
        before = [leg for leg in legs if leg.arrives_local.date() <= visit.visit_date]
        zone = max(before, key=lambda leg: leg.arrives_at).arrives_tz if before else None
    if zone is None:
        return None
    return to_utc(datetime.combine(visit.visit_date, visit.visit_time), zone)


def find_visit_warnings(
    visits: list[VisitRead], legs: list[LegRead], stays: list[StayRead], max_per_day: int
) -> list[TripWarning]:
    """Planned and visited visits that clash with the legs, have no lodging in their city, or crowd one day.

    Visits without a date, or without a time for the checks that need one, are skipped."""
    active = [v for v in visits if v.status != "missed"]
    ordered = sorted(legs, key=lambda leg: (leg.departs_at, leg.id))
    warnings: list[TripWarning] = []

    for visit in active:
        if visit.visit_date is None:
            continue
        name = visit.place.name
        when = f"{visit.visit_date:%d %b}" + (f" {visit.visit_time:%H:%M}" if visit.visit_time else "")
        instant = _visit_instant(visit, stays, ordered)
        if instant is not None and ordered:
            if instant < ordered[0].arrives_at:
                warnings.append(TripWarning(
                    kind="visit_before_arrival", visit_id=visit.id,
                    message=f"{name} ({when}) is before you arrive in {ordered[0].destination}",
                ))
            elif instant > ordered[-1].departs_at:
                warnings.append(TripWarning(
                    kind="visit_after_departure", visit_id=visit.id,
                    message=f"{name} ({when}) is after your last departure from {ordered[-1].origin}",
                ))
            overlap = next((leg for leg in ordered if leg.departs_at <= instant <= leg.arrives_at), None)
            if overlap is not None:
                warnings.append(TripWarning(
                    kind="visit_overlaps_leg", visit_id=visit.id, leg_id=overlap.id,
                    message=f"{name} ({when}) falls during {overlap.origin} → {overlap.destination}",
                ))
        if stays and visit.place.city:
            lodging = [s for s in stays if s.check_in_local.date() <= visit.visit_date <= s.check_out_local.date()]
            if not any(_same_place(visit.place.city, s.place.city) for s in lodging):
                warnings.append(TripWarning(
                    kind="visit_without_stay", visit_id=visit.id,
                    message=f"{name} ({when}) is in {visit.place.city} but no stay there covers that day",
                ))

    per_day: dict[date, int] = {}
    for visit in active:
        if visit.visit_date is not None:
            per_day[visit.visit_date] = per_day.get(visit.visit_date, 0) + 1
    for day, count in sorted(per_day.items()):
        if count > max_per_day:
            warnings.append(TripWarning(kind="too_many_visits", message=f"{count} visits on {day:%d %b} (more than {max_per_day})"))
    return warnings


def _event_wall_time(event, local_zone: ZoneInfo) -> datetime:
    """An event's start as wall-clock time in its own zone (stored starts are naive local time)."""
    zone = ZoneInfo(event.timezone) if event.timezone else local_zone
    return event.start_datetime.replace(tzinfo=local_zone).astimezone(zone).replace(tzinfo=None)


def find_outside_dates_warnings(
    legs: list[LegRead], stays: list[StayRead], visits: list[VisitRead], start: date, end: date,
) -> list[TripWarning]:
    """Legs, stays and dated visits (missed ones aside) that fall on days outside the trip's dates."""
    def outside(first: date, last: date) -> bool:
        return first < start or last > end

    warnings: list[TripWarning] = []
    for leg in sorted(legs, key=lambda leg: (leg.departs_at, leg.id)):
        if outside(leg.departs_local.date(), leg.arrives_local.date()):
            warnings.append(TripWarning(
                kind="outside_trip_dates", leg_id=leg.id,
                message=f"Leg {leg.origin} to {leg.destination} ({leg.departs_local:%d %b}) is outside the trip dates",
            ))
    for stay in sorted(stays, key=lambda stay: (stay.check_in_at, stay.id)):
        if outside(stay.check_in_local.date(), stay.check_out_local.date()):
            warnings.append(TripWarning(
                kind="outside_trip_dates", stay_id=stay.id,
                message=f"Stay at {stay.place.name} ({stay.check_in_local:%d %b} to {stay.check_out_local:%d %b}) is outside the trip dates",
            ))
    for visit in sorted((v for v in visits if v.visit_date and v.status != "missed"), key=lambda v: (v.visit_date, v.id)):
        if outside(visit.visit_date, visit.visit_date):
            warnings.append(TripWarning(
                kind="outside_trip_dates", visit_id=visit.id,
                message=f"{visit.place.name} ({visit.visit_date:%d %b}) is outside the trip dates",
            ))
    return warnings


def find_chain_warnings(legs: list[LegRead]) -> list[TripWarning]:
    """A leg that starts somewhere other than where the previous one ended."""
    ordered = sorted(legs, key=lambda leg: (leg.departs_at, leg.id))
    return [
        TripWarning(
            kind="broken_leg_chain", leg_id=nxt.id,
            message=f"A leg ends in {prev.destination} but the next one starts in {nxt.origin} ({nxt.departs_local:%d %b})",
        )
        for prev, nxt in zip(ordered, ordered[1:])
        if not (_same_place(prev.destination, nxt.origin) or _same_place(nxt.origin, prev.destination))
    ]


def find_stay_overlap_warnings(stays: list[StayRead]) -> list[TripWarning]:
    """A stay that begins before the previous one has ended."""
    ordered = sorted(stays, key=lambda stay: (stay.check_in_at, stay.id))
    return [
        TripWarning(
            kind="overlapping_stays", stay_id=nxt.id,
            message=f"{nxt.place.name} (from {nxt.check_in_local:%d %b}) overlaps {prev.place.name} (until {prev.check_out_local:%d %b})",
        )
        for prev, nxt in zip(ordered, ordered[1:])
        if nxt.check_in_at < prev.check_out_at
    ]


def find_unpaid_stay_warnings(
    stays: list[StayRead], paid_stay_ids: set[int], trip_start: date, today: date, days: int,
) -> list[TripWarning]:
    """Stays still to begin that have no linked charge, under the same window as unpaid legs."""
    if days <= 0 or (trip_start - today).days > days:
        return []
    return [
        TripWarning(
            kind="stay_not_paid", stay_id=stay.id,
            message=f"{stay.place.name} (from {stay.check_in_local:%d %b}) has no linked charge: not booked or paid yet?",
        )
        for stay in sorted(stays, key=lambda stay: (stay.check_in_at, stay.id))
        if stay.id not in paid_stay_ids and stay.check_in_local.date() >= today
    ]


# Modes that come with a booking; walking-style legs (car, other) never get a reference.
_BOOKED_MODES = {"flight", "train", "bus", "ferry"}


def find_booking_reference_warnings(
    legs: list[LegRead], stays: list[StayRead], trip_start: date, today: date, days: int,
) -> list[TripWarning]:
    """Booked legs and stays still to come with neither a booking reference nor a booking link."""
    if days <= 0 or (trip_start - today).days > days:
        return []
    warnings = [
        TripWarning(
            kind="no_booking_reference", leg_id=leg.id,
            message=f"{leg.origin} to {leg.destination} ({leg.departs_local:%d %b}) has no booking reference or link",
        )
        for leg in sorted(legs, key=lambda leg: (leg.departs_at, leg.id))
        if leg.mode in _BOOKED_MODES and not (leg.booking_ref or leg.booking_url) and leg.departs_local.date() >= today
    ]
    warnings.extend(
        TripWarning(
            kind="no_booking_reference", stay_id=stay.id,
            message=f"{stay.place.name} (from {stay.check_in_local:%d %b}) has no booking reference or link",
        )
        for stay in sorted(stays, key=lambda stay: (stay.check_in_at, stay.id))
        if not (stay.booking_ref or stay.booking_url) and stay.check_in_local.date() >= today
    )
    return warnings


def find_visit_overlap_warnings(visits: list[VisitRead], duration_min: int) -> list[TripWarning]:
    """Timed visits of one day whose slots (the default event length) run into the next one."""
    timed = sorted(
        (v for v in visits if v.visit_date and v.visit_time and v.status != "missed"),
        key=lambda v: (v.visit_date, v.visit_time, v.id),
    )
    warnings: list[TripWarning] = []
    for prev, nxt in zip(timed, timed[1:]):
        if prev.visit_date != nxt.visit_date:
            continue
        ends = datetime.combine(prev.visit_date, prev.visit_time) + timedelta(minutes=duration_min)
        if datetime.combine(nxt.visit_date, nxt.visit_time) < ends:
            warnings.append(TripWarning(
                kind="visits_overlap", visit_id=nxt.id,
                message=f"{nxt.place.name} ({nxt.visit_time:%H:%M}) starts before {prev.place.name} ({prev.visit_time:%H:%M}) is over",
            ))
    return warnings


def find_unpaid_leg_warnings(
    legs: list[LegRead], paid_leg_ids: set[int], trip_start: date, today: date, days: int,
) -> list[TripWarning]:
    """Legs still to travel that have no linked charge, once the trip starts within `days` days (0 turns it off)."""
    if days <= 0 or (trip_start - today).days > days:
        return []
    return [
        TripWarning(
            kind="leg_not_paid", leg_id=leg.id,
            message=f"{leg.origin} to {leg.destination} ({leg.departs_local:%d %b}) has no linked charge: not bought yet?",
        )
        for leg in sorted(legs, key=lambda leg: (leg.departs_at, leg.id))
        if leg.id not in paid_leg_ids and leg.departs_local.date() >= today
    ]


def find_event_warnings(visits: list[VisitRead], events: dict[int, object], today: date, local_zone: ZoneInfo) -> list[TripWarning]:
    """Visits whose calendar event is missing or says something different (only what Alfred's local copy holds).

    `events` maps event id -> EventRead for the visits' linked events; legs and stays are never compared."""
    warnings: list[TripWarning] = []
    for visit in visits:
        if visit.visit_date is None or visit.visit_time is None or visit.status == "missed":
            continue
        when = f"{visit.visit_date:%d %b} {visit.visit_time:%H:%M}"
        if visit.calendar_event_id is None:
            if visit.status == "planned" and visit.visit_date >= today:
                warnings.append(TripWarning(
                    kind="no_calendar_event", visit_id=visit.id,
                    message=f"{visit.place.name} ({when}) has no calendar event",
                ))
            continue
        event = events.get(visit.calendar_event_id)
        if event is None:
            continue
        if _event_wall_time(event, local_zone) == datetime.combine(visit.visit_date, visit.visit_time):
            continue
        touchable = not (event.recurrence_rule or event.invitees or event.all_day)
        warnings.append(TripWarning(
            kind="linked_event_mismatch" if touchable else "linked_event_not_updated", visit_id=visit.id,
            message=(
                f"{visit.place.name} ({when}) and its calendar event show different times"
                if touchable else
                f"{visit.place.name} ({when}) differs from its calendar event, which is recurring, has guests or is all-day, so Alfred leaves it alone"
            ),
        ))
    return warnings
