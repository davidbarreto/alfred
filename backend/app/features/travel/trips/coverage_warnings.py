"""Pure functions: warnings about gaps in a trip's lodging and about visits that cannot work. No DB or IO."""
from datetime import date, datetime, timedelta

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
