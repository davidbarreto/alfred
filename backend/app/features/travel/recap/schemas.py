from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.features.travel.transaction_links.schemas import Cost, KindCost
from app.features.travel.trips.schemas import TripStatus

Missing = Literal["grade", "notes"]


class RecapItem(BaseModel):
    """A visit or stay that still lacks a grade or notes."""

    kind: Literal["visit", "stay"]
    id: int
    place_id: int
    place_name: str
    day: date | None
    missing: list[Missing]


class RecapHighlight(BaseModel):
    kind: Literal["visit", "stay"]
    id: int
    place_id: int
    place_name: str
    grade: int


class TripRecap(BaseModel):
    trip_id: int
    name: str
    start_date: date
    end_date: date
    status: TripStatus
    days: int
    leg_count: int
    stay_count: int
    visits_visited: int
    visits_missed: int
    visits_planned: int
    cities: list[str]
    countries: list[str]
    spend: Cost
    spend_by_kind: list[KindCost]
    # Charges with the trip's default tags that no leg, stay or visit counts: a separate part, not in `spend`.
    spend_tagged: Cost
    # `spend` plus `spend_tagged`.
    spend_overall: Cost
    # Visited visits and stays with no grade and/or no notes: what is left to write down after the trip.
    to_complete: list[RecapItem]
    highlights: list[RecapHighlight]
