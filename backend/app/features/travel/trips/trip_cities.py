"""Pure function: the cities of a trip and the role each plays. No DB or IO."""
from datetime import date, datetime, time, timezone
from typing import Literal

from pydantic import BaseModel

from app.features.travel.cities.schemas import CityRef
from app.features.travel.legs.schemas import LegRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.visits.schemas import VisitRead

CityRole = Literal["stayed", "passed"]

# Visits with no day come after everything dated.
_UNDATED = datetime.max.replace(tzinfo=timezone.utc)


class TripCity(BaseModel):
    city: CityRef
    role: CityRole


def build_trip_cities(
    legs: list[LegRead], stays: list[StayRead], visits: list[VisitRead], today: date, end_date: date
) -> tuple[list[TripCity], int]:
    """The trip's cities by first appearance in time, and how many leg ends have no city.

    `stayed`: a stay there, a visited visit, or a planned visit while the trip has not ended. `passed`: only a leg
    end (or only missed visits, or planned ones on a finished trip, which are not listed at all unless a leg ends there).
    """
    ended = end_date < today
    appearances: list[tuple[datetime, int, CityRef, bool]] = []  # (when, order, city, counts as staying)
    unmatched = 0
    for leg in legs:
        for city, when in ((leg.origin_city, leg.departs_at), (leg.destination_city, leg.arrives_at)):
            if city is None:
                unmatched += 1
            else:
                appearances.append((when, len(appearances), city, False))
    for stay in stays:
        appearances.append((stay.check_in_at, len(appearances), stay.place.city, True))
    for visit in visits:
        when = datetime.combine(visit.visit_date, visit.visit_time or time.min, tzinfo=timezone.utc) if visit.visit_date else _UNDATED
        stays_there = visit.status == "visited" or (visit.status == "planned" and not ended)
        appearances.append((when, len(appearances), visit.place.city, stays_there))

    appearances.sort(key=lambda a: (a[0], a[1]))
    cities: dict[int, CityRef] = {}
    stayed: set[int] = set()
    for _, _, city, counts in appearances:
        cities.setdefault(city.id, city)
        if counts:
            stayed.add(city.id)
    leg_cities = {c.id for leg in legs for c in (leg.origin_city, leg.destination_city) if c is not None}
    result = [
        TripCity(city=city, role="stayed" if city_id in stayed else "passed")
        for city_id, city in cities.items() if city_id in stayed or city_id in leg_cities
    ]
    return result, unmatched
