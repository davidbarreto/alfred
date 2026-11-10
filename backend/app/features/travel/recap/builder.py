"""Pure: turn a trip with all its visits, plus its costs, into a recap. No DB or IO."""
from app.features.travel.recap.schemas import RecapHighlight, RecapItem, TripRecap
from app.features.travel.transaction_links.schemas import Cost, TripCosts
from app.features.travel.trips.schemas import TripDetail

# Grades at or above this are listed as highlights.
HIGHLIGHT_GRADE = 4


def _distinct(values) -> list[str]:
    seen: dict[str, str] = {}
    for value in values:
        if value and value.strip().lower() not in seen:
            seen[value.strip().lower()] = value.strip()
    return sorted(seen.values(), key=str.lower)


def build_recap(trip: TripDetail, costs: TripCosts | None) -> TripRecap:
    visited = [v for v in trip.visits if v.status == "visited"]
    # Where the trip actually went: stays, and visits that happened (a missed or planned one did not).
    places = [s.place for s in trip.stays]
    place_cities = _distinct([*(p.city for p in places), *(v.place.city for v in visited)])
    countries = _distinct([*(p.country for p in places), *(v.place.country for v in visited)])

    to_complete: list[RecapItem] = []
    for v in visited:
        missing = [m for m, absent in (("grade", v.grade is None), ("notes", not (v.notes or "").strip())) if absent]
        if missing:
            to_complete.append(RecapItem(
                kind="visit", id=v.id, place_id=v.place_id, place_name=v.place.name, day=v.visit_date, missing=missing,
            ))
    for s in trip.stays:
        missing = [m for m, absent in (("grade", s.grade is None), ("notes", not (s.notes or "").strip())) if absent]
        if missing:
            to_complete.append(RecapItem(
                kind="stay", id=s.id, place_id=s.place_id, place_name=s.place.name, day=s.check_in_local.date(), missing=missing,
            ))
    to_complete.sort(key=lambda item: (item.day is None, item.day, item.kind, item.id))

    highlights = [
        RecapHighlight(kind="visit", id=v.id, place_id=v.place_id, place_name=v.place.name, grade=v.grade)
        for v in visited if v.grade is not None and v.grade >= HIGHLIGHT_GRADE
    ] + [
        RecapHighlight(kind="stay", id=s.id, place_id=s.place_id, place_name=s.place.name, grade=s.grade)
        for s in trip.stays if s.grade is not None and s.grade >= HIGHLIGHT_GRADE
    ]
    highlights.sort(key=lambda h: (-h.grade, h.place_name.lower()))

    all_visits = trip.visits
    return TripRecap(
        trip_id=trip.id, name=trip.name, start_date=trip.start_date, end_date=trip.end_date, status=trip.status,
        days=(trip.end_date - trip.start_date).days + 1, leg_count=len(trip.legs), stay_count=len(trip.stays),
        visits_visited=len(visited), visits_missed=sum(v.status == "missed" for v in all_visits),
        visits_planned=sum(v.status == "planned" for v in all_visits),
        cities=place_cities, countries=countries,
        spend=costs.total if costs else Cost(), spend_by_kind=costs.by_kind if costs else [],
        to_complete=to_complete, highlights=highlights,
    )
