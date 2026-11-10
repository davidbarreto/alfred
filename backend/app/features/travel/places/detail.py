from app.features.travel.places.schemas import PlaceRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.visits.schemas import VisitRead


class PlaceDetail(PlaceRead):
    """A place with its history: every visit and stay, most recent first."""

    visits: list[VisitRead]
    stays: list[StayRead]
