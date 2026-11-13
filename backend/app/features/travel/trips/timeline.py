"""Pure functions: a trip's chronological timeline and its gap warnings. No DB or IO."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Literal

from pydantic import BaseModel

from app.features.travel.legs.schemas import LegRead
from app.features.travel.links import maps_directions_url, maps_search_url, place_maps_url
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.zones import to_local
from app.shared.timezone import local_timezone

# Arriving this long before the room is ready is worth a heads-up (luggage storage, a cafe).
LONG_WAIT_BEFORE_CHECK_IN = timedelta(hours=4)
TIGHT_CONNECTION = timedelta(minutes=90)
# How far from check-in a leg is still considered "the arrival for that stay".
ARRIVAL_WINDOW = timedelta(hours=24)

TimelineKind = Literal["leg", "arrival", "check_in", "check_out", "leave_home"]
WarningKind = Literal[
    "long_wait_before_check_in", "tight_connection", "arrives_after_check_out", "overlapping_legs",
    "uncovered_night", "no_return_leg",
    "visit_before_arrival", "visit_after_departure", "visit_overlaps_leg", "visit_without_stay", "too_many_visits",
    "no_calendar_event", "linked_event_mismatch", "linked_event_not_updated", "leg_not_paid", "outside_trip_dates",
]


class TimelineItem(BaseModel):
    kind: TimelineKind
    at: datetime
    local: datetime
    timezone: str
    title: str
    subtitle: str | None = None
    ref_id: int
    links: dict[str, str] = {}
    # Airport transfer this row is about (where it goes), shown above its Maps links.
    transfer_label: str | None = None
    # Hours this row's zone is ahead of (+) or behind (-) home, e.g. "+1h"; None when the same as home.
    home_offset: str | None = None
    # One-line advice on arrival rows when the difference is large.
    sleep_hint: str | None = None
    # Messages of the trip warnings that point at this row, so the portal can highlight it.
    warnings: list[str] = []


class TripWarning(BaseModel):
    kind: WarningKind
    message: str
    leg_id: int | None = None
    stay_id: int | None = None
    visit_id: int | None = None


def _same_place(name: str | None, city: str | None) -> bool:
    if not name or not city:
        return False
    a, b = name.strip().lower(), city.strip().lower()
    return bool(a) and bool(b) and (a in b or b in a)


# From this many hours of difference an arrival row gets a sleep hint.
SLEEP_HINT_HOURS = 3


def _offset_hours(instant: datetime, zone: str, home: ZoneInfo) -> float:
    delta = instant.astimezone(ZoneInfo(zone)).utcoffset() - instant.astimezone(home).utcoffset()  # type: ignore[operator]
    return delta.total_seconds() / 3600


def _format_offset(hours: float) -> str:
    whole = f"{abs(hours):g}"
    return f"{'+' if hours > 0 else '-'}{whole}h"


def _add_home_offsets(items: list["TimelineItem"], home: ZoneInfo) -> None:
    for item in items:
        hours = _offset_hours(item.at, item.timezone, home)
        if hours == 0:
            continue
        item.home_offset = _format_offset(hours)
        if item.kind == "arrival" and abs(hours) >= SLEEP_HINT_HOURS:
            direction = "ahead of" if hours > 0 else "behind"
            item.sleep_hint = f"{item.home_offset} {direction} home: expect jet lag, try to sleep on local time"


def _hours(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if hours else f"{rest} min"


def _airport(code: str | None, city: str) -> str:
    return f"{code} airport" if code else f"{city} airport"


def _lodging(place: PlaceRead) -> str:
    """What to type into Maps for a stay: the address or coordinates when known, else name + city."""
    if place.lat is not None and place.lng is not None:
        return f"{place.lat},{place.lng}"
    return " ".join(p for p in (place.name, place.address or place.city) if p)


def _transfer_links(origin: str, destination: str) -> dict[str, str]:
    """The options to compare in Maps for one transfer: public transport, taxi/car and walking."""
    return {
        "directions": maps_directions_url(origin, destination, "transit"),
        "drive": maps_directions_url(origin, destination, "driving"),
        "walk": maps_directions_url(origin, destination, "walking"),
    }


def _stay_before(leg: LegRead, stays: list[StayRead]) -> StayRead | None:
    """The stay in the leg's origin city the traveler is leaving from (the latest one begun by departure)."""
    started = [s for s in stays if _same_place(leg.origin, s.place.city) and s.check_in_at <= leg.departs_at]
    return max(started, key=lambda s: s.check_in_at, default=None)


def _stay_after(leg: LegRead, stays: list[StayRead]) -> StayRead | None:
    """The stay in the leg's destination city the traveler is heading to (the first check-in near arrival)."""
    near = [
        s for s in stays
        if _same_place(leg.destination, s.place.city) and timedelta(hours=-1) <= s.check_in_at - leg.arrives_at <= ARRIVAL_WINDOW
    ]
    if near:
        return min(near, key=lambda s: s.check_in_at)
    # Checking in more than a day later still means heading to that hotel: the first stay there that is not over yet.
    later = [s for s in stays if _same_place(leg.destination, s.place.city) and s.check_out_at > leg.arrives_at]
    return min(later, key=lambda s: s.check_in_at, default=None)


def _food_links(near: str) -> dict[str, str]:
    return {"cafes": maps_search_url(f"cafe near {near}"), "restaurants": maps_search_url(f"restaurants near {near}")}


def _leg_item(leg: LegRead, stays: list[StayRead], home_address: str | None, is_first: bool) -> TimelineItem:
    links: dict[str, str] = {}
    label = None
    if leg.mode == "flight":
        # Getting to the airport: from the hotel the traveler is leaving, or from home on the first leg.
        airport = _airport(leg.origin_code, leg.origin)
        links.update(_food_links(airport))
        stay = _stay_before(leg, stays)
        if stay is not None:
            links.update(_transfer_links(_lodging(stay.place), airport))
            label = f"{stay.place.name} \u2192 {airport}"
        elif is_first and home_address:
            links.update(_transfer_links(home_address, airport))
            label = f"Home \u2192 {airport}"
    else:
        links.update(_transfer_links(leg.origin, leg.destination))
    if leg.check_flight_url:
        links["check_flight"] = leg.check_flight_url
    ident = " ".join(part for part in (leg.carrier, leg.number) if part)
    return TimelineItem(
        kind="leg", at=leg.departs_at, local=leg.departs_local, timezone=leg.departs_tz,
        title=f"{leg.origin} \u2192 {leg.destination}", subtitle=" \u00b7 ".join(p for p in (leg.mode, ident) if p),
        ref_id=leg.id, links=links, transfer_label=label,
    )


def _arrival_item(leg: LegRead, stays: list[StayRead]) -> TimelineItem:
    # A flight lands at an airport: show the area around it, not the whole city.
    links = {"map": maps_search_url(_airport(leg.destination_code, leg.destination) if leg.mode == "flight" else leg.destination)}
    if leg.mode == "flight":
        links.update(_food_links(_airport(leg.destination_code, leg.destination)))
    label = None
    stay = _stay_after(leg, stays) if leg.mode == "flight" else None
    if stay is not None:
        airport = _airport(leg.destination_code, leg.destination)
        links.update(_transfer_links(airport, _lodging(stay.place)))
        label = f"{airport} \u2192 {stay.place.name}"
    return TimelineItem(
        kind="arrival", at=leg.arrives_at, local=leg.arrives_local, timezone=leg.arrives_tz,
        title=f"Arrive: {leg.destination}", subtitle=f"{leg.origin} \u2192 {leg.destination}", ref_id=leg.id,
        links=links, transfer_label=label,
    )


def _stay_items(stay: StayRead) -> list[TimelineItem]:
    place = stay.place
    near = " ".join(p for p in (place.name, place.city) if p)
    links = {
        "map": place_maps_url(place.name, place.city, place.maps_url, place.lat, place.lng),
        **_food_links(near),
        "luggage": maps_search_url(f"luggage storage near {near}"),
        "pharmacy": maps_search_url(f"pharmacy near {near}"),
        "supermarket": maps_search_url(f"supermarket near {near}"),
        "atm": maps_search_url(f"ATM near {near}"),
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


def leave_home_at(legs: list[LegRead], leave_minutes: int) -> datetime | None:
    """When to leave home for the trip's first leg, if that leg is a flight (the buffer and the ride to the airport)."""
    first = min(legs, key=lambda leg: (leg.departs_at, leg.id), default=None)
    if first is None or first.mode != "flight":
        return None
    return first.departs_at - timedelta(minutes=leave_minutes)


# Which timeline rows a warning points at: (item kind, which id of the warning identifies it).
_WARNING_ROWS = {
    "long_wait_before_check_in": (("arrival", "leg_id"), ("check_in", "stay_id")),
    "arrives_after_check_out": (("arrival", "leg_id"), ("check_out", "stay_id")),
    "tight_connection": (("leg", "leg_id"),),
    "overlapping_legs": (("leg", "leg_id"),),
}


def _flag_warnings(items: list[TimelineItem], warnings: list[TripWarning]) -> None:
    for warning in warnings:
        for kind, id_field in _WARNING_ROWS.get(warning.kind, ()):
            ref_id = getattr(warning, id_field)
            for item in items:
                if item.kind == kind and item.ref_id == ref_id:
                    item.warnings.append(warning.message)


def build_timeline(
    legs: list[LegRead],
    stays: list[StayRead],
    leave_home: datetime | None = None,
    home_address: str | None = None,
    warnings: list[TripWarning] | None = None,
    home_zone: ZoneInfo | None = None,
) -> list[TimelineItem]:
    first_id = min(legs, key=lambda leg: (leg.departs_at, leg.id)).id if legs else None
    items = [_leg_item(leg, stays, home_address, leg.id == first_id) for leg in legs]
    items.extend(_arrival_item(leg, stays) for leg in legs)
    if leave_home is not None:
        first = min(legs, key=lambda leg: (leg.departs_at, leg.id))
        items.append(TimelineItem(
            kind="leave_home", at=leave_home, local=to_local(leave_home, first.departs_tz), timezone=first.departs_tz,
            title="Leave home for the airport", subtitle=f"{first.origin} \u2192 {first.destination}", ref_id=first.id,
        ))
    for stay in stays:
        items.extend(_stay_items(stay))
    _flag_warnings(items, warnings or [])
    _add_home_offsets(items, home_zone or local_timezone())
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
