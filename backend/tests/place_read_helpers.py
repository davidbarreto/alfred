"""Shared builders for place read models in API tests."""
from datetime import date, datetime, timezone

from app.features.location.places.schemas import PlaceRead, PlaceToday
from app.features.organizer.everyday_places.schemas import EverydayPlaceRead, PlaceCategory

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
CITY = {"id": 15, "name": "Hometown", "country": {"id": 1, "name": "Testland", "code": "TL"}}


def place_fields(**kwargs) -> dict:
    fields = dict(
        id=1, name="Market", kind="supermarket", city=CITY, address=None, maps_url=None,
        opening_hours={"mon": [["08:00", "20:00"]]}, notes=None, active=True,
        today=PlaceToday(date=date(2026, 11, 23), hours="08:00-20:00", open_now=True),
        created_at=NOW, updated_at=NOW,
    )
    fields.update(kwargs)
    return fields


def place_read(**kwargs) -> PlaceRead:
    return PlaceRead(**place_fields(**kwargs))


def everyday_read(everyday: bool = True, categories=None, **kwargs) -> EverydayPlaceRead:
    return EverydayPlaceRead(
        **place_fields(**kwargs), everyday=everyday,
        categories=categories if categories is not None else [PlaceCategory(id=1, name="groceries")],
    )
