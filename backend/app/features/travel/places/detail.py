from app.features.travel.places.schemas import TravelPlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.visits.schemas import VisitRead


class TravelPlaceDetail(TravelPlaceRead):
    """A place with its history: every visit and stay, most recent first."""

    visits: list[VisitRead]
    stays: list[StayRead]
