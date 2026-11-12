"""Pure function: group a trip's undated planned visits and wishlist visits by the cities it stays in. No DB or IO."""
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.schemas import IdeaGroup
from app.features.travel.visits.schemas import VisitRead

OTHER_CITY = "Other places"


def build_ideas(trip_visits: list[VisitRead], wishlist: list[VisitRead], stays: list[StayRead]) -> list[IdeaGroup]:
    """Trip visits without a day, plus wishlist visits in a stay city, grouped by city (stay order, then the rest)."""
    stay_cities: dict[str, str] = {}
    for stay in sorted(stays, key=lambda s: s.check_in_at):
        if stay.place.city:
            stay_cities.setdefault(stay.place.city.lower(), stay.place.city)

    candidates = [v for v in trip_visits if v.visit_date is None and v.status == "planned"]
    candidates += [v for v in wishlist if v.place.city and v.place.city.lower() in stay_cities]

    groups: dict[str, list[VisitRead]] = {}
    for visit in candidates:
        key = (visit.place.city or "").lower()
        groups.setdefault(key if key in stay_cities else "", []).append(visit)

    result = [IdeaGroup(city=stay_cities[key], visits=groups[key]) for key in stay_cities if key in groups]
    if "" in groups:
        result.append(IdeaGroup(city=OTHER_CITY, visits=groups[""]))
    return result
