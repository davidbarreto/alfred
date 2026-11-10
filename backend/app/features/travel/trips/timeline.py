"""Pure functions: a trip's chronological timeline and its gap warnings. No DB or IO."""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel

from app.features.travel.legs.schemas import LegRead
from app.features.travel.links import maps_directions_url, maps_search_url, place_maps_url
from app.features.travel.stays.schemas import StayRead
from app.features.travel.zones import to_local

# Arriving this long before the room is ready is worth a heads-up (luggage storage, a cafe).
LONG_WAIT_BEFORE_CHECK_IN = timedelta(hours=4)
TIGHT_CONNECTION = timedelta(minutes=90)
# How far from check-in a leg is still considered "the arrival for that stay".
ARRIVAL_WINDOW = timedelta(hours=24)

TimelineKind = Literal["leg", "check_in", "check_out"]
WarningKind = Literal["long_wait_before_check_in", "tight_connection", "arrives_after_check_out", "overlapping_legs"]


class TimelineItem(BaseModel):
    kind: TimelineKind
    at: datetime
    local: datetime
    timezone: str
    title: str
    subtitle: str | None = None
    ref_id: int
    links: dict[str, str] = {}


class TripWarning(BaseModel):
    kind: WarningKind
    message: str
    leg_id: int | None = None
    stay_id: int | None = None


def _same_place(name: str | None, city: str | None) -> bool:
    if not name or not city:
        return False
    a, b = name.strip().lower(), city.strip().lower()
    return bool(a) and bool(b) and (a in b or b in a)


def _hours(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if hours else f"{rest} min"


def _leg_item(leg: LegRead) -> TimelineItem:
    links = {"directions": maps_directions_url(leg.origin, leg.destination)}
    if leg.check_flight_url:
        links["check_flight"] = leg.check_flight_url
    ident = " ".join(part for part in (leg.carrier, leg.number) if part)
    return TimelineItem(
        kind="leg", at=leg.departs_at, local=leg.departs_local, timezone=leg.departs_tz,
        title=f"{leg.origin} → {leg.destination}", subtitle=" · ".join(p for p in (leg.mode, ident) if p),
        ref_id=leg.id, links=links,
    )


def _stay_items(stay: StayRead) -> list[TimelineItem]:
    place = stay.place
    near = " ".join(p for p in (place.name, place.city) if p)
    links = {
        "map": place_maps_url(place.name, place.city, place.maps_url, place.lat, place.lng),
        "cafes": maps_search_url(f"cafe near {near}"),
        "luggage": maps_search_url(f"luggage storage near {near}"),
    }
    return [
        TimelineItem(
            kind="check_in", at=stay.check_in_at, local=stay.check_in_local, timezone=stay.timezone,
            title=f"Check in: {place.name}", subtitle=place.city, ref_id=stay.id, links=links,
        ),
        TimelineItem(
            kind="check_out", at=stay.check_out_at, local=stay.check_out_local, timezone=stay.timezone,
            title=f"Check out: {place.name}", subtitle=place.city, ref_id=stay.id, links=links,
        ),
    ]


def build_timeline(legs: list[LegRead], stays: list[StayRead]) -> list[TimelineItem]:
    items = [_leg_item(leg) for leg in legs]
    for stay in stays:
        items.extend(_stay_items(stay))
    return sorted(items, key=lambda item: (item.at, item.ref_id))


def find_warnings(legs: list[LegRead], stays: list[StayRead]) -> list[TripWarning]:
    """Only from data that exists: no stay means no check-in warning, no legs means no leg warnings."""
    warnings: list[TripWarning] = []
    ordered = sorted(legs, key=lambda leg: (leg.departs_at, leg.id))

    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt.departs_at < prev.arrives_at:
            warnings.append(TripWarning(
                kind="overlapping_legs", leg_id=nxt.id,
                message=f"{nxt.origin} → {nxt.destination} departs before {prev.origin} → {prev.destination} arrives",
            ))
            continue
        connected = _same_place(prev.destination, nxt.origin) or _same_place(nxt.origin, prev.destination)
        gap = nxt.departs_at - prev.arrives_at
        if connected and gap < TIGHT_CONNECTION:
            warnings.append(TripWarning(
                kind="tight_connection", leg_id=nxt.id,
                message=f"Only {_hours(gap)} to connect in {prev.destination}",
            ))

    for stay in stays:
        city = stay.place.city
        for leg in ordered:
            if not _same_place(leg.destination, city):
                continue
            wait = stay.check_in_at - leg.arrives_at
            if timedelta(0) <= wait <= ARRIVAL_WINDOW and wait > LONG_WAIT_BEFORE_CHECK_IN:
                warnings.append(TripWarning(
                    kind="long_wait_before_check_in", leg_id=leg.id, stay_id=stay.id,
                    message=(
                        f"Arrives in {leg.destination} {_hours(wait)} before check-in at {stay.place.name} "
                        f"({to_local(stay.check_in_at, stay.timezone):%H:%M})"
                    ),
                ))
            if leg.departs_at < stay.check_out_at < leg.arrives_at:
                warnings.append(TripWarning(
                    kind="arrives_after_check_out", leg_id=leg.id, stay_id=stay.id,
                    message=f"Arrives in {leg.destination} after check-out from {stay.place.name}",
                ))
    return warnings
