"""Pure function: group a trip's undated planned visits and wishlist visits by the cities it stays in. No DB or IO."""
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.schemas import IdeaGroup
from app.features.travel.visits.schemas import VisitRead

OTHER_CITY = "Other places"


def build_ideas(trip_visits: list[VisitRead], wishlist: list[VisitRead], stays: list[StayRead]) -> list[IdeaGroup]:
    """Trip visits without a day, plus wishlist visits in a stay city, grouped by city (stay order, then the rest)."""
    stay_cities: dict[int, str] = {}
    for stay in sorted(stays, key=lambda s: s.check_in_at):
        stay_cities.setdefault(stay.place.city.id, stay.place.city.name)

    candidates = [v for v in trip_visits if v.visit_date is None and v.status == "planned"]
    candidates += [v for v in wishlist if v.place.city.id in stay_cities]

    groups: dict[int | None, list[VisitRead]] = {}
    for visit in candidates:
        key = visit.place.city.id
        groups.setdefault(key if key in stay_cities else None, []).append(visit)

    result = [IdeaGroup(city=stay_cities[key], visits=groups[key]) for key in stay_cities if key in groups]
    if None in groups:
        result.append(IdeaGroup(city=OTHER_CITY, visits=groups[None]))
    return result
