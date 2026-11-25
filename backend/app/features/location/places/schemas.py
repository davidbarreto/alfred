from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, Field, computed_field, field_validator

from app.features.location.cities.schemas import CityRef
from app.features.location.places.constants import DEFAULT_KIND, PLACE_KINDS, PlaceKind
from app.features.location.places.coordinates import parse_coordinates
from app.features.location.places.hours import format_hours
from app.shared.utils.links import place_maps_url

# Latitude, longitude. Text like "41.1579, -8.6291" is accepted too; left empty, the Maps link's are used if it has any.
Coordinates = tuple[Annotated[float, Field(ge=-90, le=90)], Annotated[float, Field(ge=-180, le=180)]]


def clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("name must not be blank")
    if len(cleaned) > 200:
        raise ValueError("name must be at most 200 characters")
    return cleaned


def clean_kind(value: Any) -> Any:
    """Trim and lowercase before the Literal check, so "Work " is work."""
    return value.strip().lower() if isinstance(value, str) else value


def blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip() or None


def clean_coordinates(value: Any) -> Any:
    """ "41.1579, -8.6291" (as Google Maps copies them) or [lat, lon]; blank or null clears them."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        return parse_coordinates(value)
    return value


class PlaceCreate(BaseModel):
    name: str
    kind: PlaceKind = DEFAULT_KIND
    # Left out: the Home place's city.
    city_id: Optional[int] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    # Text ("mon-fri 08:00-20:00; sun closed; holidays closed") or the stored object; the service parses it.
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: bool = True

    _name = field_validator("name")(clean_name)
    _kind = field_validator("kind", mode="before")(clean_kind)
    _text = field_validator("address", "maps_url", "notes")(blank_to_none)
    _coords = field_validator("coordinates", mode="before")(clean_coordinates)


class PlaceUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[PlaceKind] = None
    city_id: Optional[int] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    # Null or blank clears them (the Maps link's are used again if it has any).
    coordinates: Optional[Coordinates] = None
    # A blank text or null clears the hours (unknown again).
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None

    _name = field_validator("name")(clean_name)
    _kind = field_validator("kind", mode="before")(clean_kind)
    _text = field_validator("address", "maps_url", "notes")(blank_to_none)
    _coords = field_validator("coordinates", mode="before")(clean_coordinates)


class PlaceToday(BaseModel):
    """Today's hours in the local timezone. hours: "08:00-20:00", "closed", or null when unknown."""

    date: date
    hours: Optional[str]
    holiday: Optional[str] = None
    # "holiday hours", or "holiday, hours unknown" when only the weekday hours are known.
    note: Optional[str] = None
    open_now: Optional[bool] = None


class PlaceRef(BaseModel):
    id: int
    name: str
    kind: str

    model_config = {"from_attributes": True}


class PlaceRead(BaseModel):
    id: int
    name: str
    kind: PlaceKind
    city: CityRef
    address: Optional[str]
    maps_url: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: Optional[dict[str, list[list[str]]]] = None
    notes: Optional[str]
    active: bool = True
    # Filled by the place service (it needs today's holiday); null in views that don't ask for it.
    today: Optional[PlaceToday] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def opening_hours_text(self) -> str:
        return format_hours(self.opening_hours)

    @computed_field
    @property
    def maps_link(self) -> str:
        return place_maps_url(self.name, self.city.name, self.maps_url, self.latitude, self.longitude)


class PlaceFilters:
    def __init__(
        self,
        kind: Annotated[Optional[str], Query()] = None,
        city_id: Annotated[Optional[int], Query()] = None,
        country_id: Annotated[Optional[int], Query()] = None,
        active: Annotated[Optional[bool], Query()] = None,
        q: Annotated[Optional[str], Query(description="Substring of the name, address, city or country")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.kind = parse_kind(kind)
        self.city_id = city_id
        self.country_id = country_id
        self.active = active
        self.q = q.strip() if q and q.strip() else None
        self.limit = limit
        self.offset = offset


def parse_kind(kind: Optional[str]) -> Optional[str]:
    """A kind filter, trimmed and lowercased; blank is none and an unknown kind is a 422."""
    cleaned = kind.strip().lower() if kind and kind.strip() else None
    if cleaned is not None and cleaned not in PLACE_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {', '.join(PLACE_KINDS)}",
        )
    return cleaned
