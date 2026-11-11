"""Pure function: the pins of a trip for a map (stays, visits that were not missed, flight airports). No DB or IO."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.visits.schemas import VisitPlace, VisitRead


MapScope = Literal["all", "planned", "visited", "missed"]


_RANK = {"missed": 0, "planned": 1, "visited": 2}


class MapPoint(BaseModel):
    name: str
    # What a map importer geocodes: "lat,lng" when the place has coordinates, else its address or name + city.
    address: str
    category: str
    # visited: it happened (a visited visit, a stay begun, a flight departed); missed: only marked missed;
    # planned: still ahead or not marked.
    status: Literal["planned", "visited", "missed"] = "planned"
    description: str | None = None


class TripMap(BaseModel):
    trip_id: int
    name: str
    points: list[MapPoint]


def _location(place: PlaceRead | VisitPlace) -> str:
    if place.lat is not None and place.lng is not None:
        return f"{place.lat},{place.lng}"
    address = getattr(place, "address", None)  # a visit's place slice has no address
    if address:
        return ", ".join(p for p in (place.name, address, place.city) if p)
    return ", ".join(p for p in (place.name, place.city, place.country) if p)


def _stay_text(stay: StayRead) -> str:
    return f"Stay {stay.check_in_local:%d %b} - {stay.check_out_local:%d %b} ({stay.nights} night{'s' if stay.nights != 1 else ''})"


def _visit_text(visit: VisitRead) -> str:
    day = f"{visit.visit_date:%d %b}" if visit.visit_date else "day not set"
    time = f" {visit.visit_time:%H:%M}" if visit.visit_time else ""
    return f"{visit.status.capitalize()}, {day}{time}"


def build_trip_map(
    trip_id: int,
    name: str,
    legs: list[LegRead],
    stays: list[StayRead],
    visits: list[VisitRead],
    now: datetime,
    scope: MapScope = "all",
) -> TripMap:
    """One pin per place (several stays or visits there are listed in its description), then the airports.

    scope "planned" keeps what is still ahead (the map to use during the trip), "visited" what already happened and
    "missed" the visits marked missed (the last two are for a history map after the trip). "all" is everything.
    """
    by_place: dict[int, MapPoint] = {}
    notes: dict[int, list[str]] = {}

    def add(place: PlaceRead | VisitPlace, text: str, category: str, status: str) -> None:
        if scope not in ("all", status):
            return
        if place.id not in by_place:
            by_place[place.id] = MapPoint(name=place.name, address=_location(place), category=category, status=status)
            notes[place.id] = []
        point = by_place[place.id]
        # One pin per place: visited beats planned beats missed.
        if _RANK[status] > _RANK[point.status]:
            point.status = status
        notes[place.id].append(text)

    for stay in sorted(stays, key=lambda s: s.check_in_at):
        add(stay.place, _stay_text(stay), "lodging", "visited" if stay.check_in_at <= now else "planned")
    for visit in visits:
        add(visit.place, _visit_text(visit), visit.place.kind, visit.status)
    points = list(by_place.values())
    for place_id, point in by_place.items():
        point.description = "; ".join(notes[place_id])

    airports: dict[str, MapPoint] = {}
    for leg in sorted(legs, key=lambda l: l.departs_at):
        taken = leg.departs_at <= now
        if leg.mode != "flight" or scope not in ("all", "visited" if taken else "planned"):
            continue
        for code, city in ((leg.origin_code, leg.origin), (leg.destination_code, leg.destination)):
            label = f"{code} airport" if code else f"{city} airport"
            point = airports.setdefault(label.lower(), MapPoint(name=label, address=label, category="airport"))
            if taken:
                point.status = "visited"
    points.extend(airports.values())
    return TripMap(trip_id=trip_id, name=name, points=points)
