from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.features.organizer.locations.constants import DEFAULT_KIND, LOCATION_KINDS, LocationKind
from app.features.organizer.locations.coordinates import parse_coordinates

# Latitude, longitude. Text like "41.1579, -8.6291" is accepted too; left empty, the Maps link's are used if it has any.
Coordinates = tuple[Annotated[float, Field(ge=-90, le=90)], Annotated[float, Field(ge=-180, le=180)]]


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("name must not be blank")
    if len(cleaned) > 100:
        raise ValueError("name must be at most 100 characters")
    return cleaned


def _clean_kind(value: Any) -> Any:
    """Trim and lowercase before the Literal check, so "Work " is work."""
    return value.strip().lower() if isinstance(value, str) else value


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip() or None


def _coordinates(value: Any) -> Any:
    """ "41.1579, -8.6291" (as Google Maps copies them) or [lat, lon]; blank or null clears them."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, str):
        return parse_coordinates(value)
    return value


class LocationCreate(BaseModel):
    name: str
    kind: LocationKind = DEFAULT_KIND
    address: Optional[str] = None
    maps_url: Optional[str] = None
    coordinates: Optional[Coordinates] = None
    # Text ("mon-fri 08:00-20:00; sun closed; holidays closed") or the stored object; the service parses it.
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: bool = True
    category_ids: list[int] = Field(default_factory=list)

    _name = field_validator("name")(_clean_name)
    _kind = field_validator("kind", mode="before")(_clean_kind)
    _text = field_validator("address", "maps_url", "notes")(_blank_to_none)
    _coords = field_validator("coordinates", mode="before")(_coordinates)


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[LocationKind] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    # Null or blank clears them (the Maps link's are used again if it has any).
    coordinates: Optional[Coordinates] = None
    # A blank text or null clears the hours (unknown again).
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    # Replaces the whole list when given.
    category_ids: Optional[list[int]] = None

    _name = field_validator("name")(_clean_name)
    _kind = field_validator("kind", mode="before")(_clean_kind)
    _text = field_validator("address", "maps_url", "notes")(_blank_to_none)
    _coords = field_validator("coordinates", mode="before")(_coordinates)


class LocationCategoriesUpdate(BaseModel):
    category_ids: list[int]


class LocationCategory(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class LocationToday(BaseModel):
    """Today's hours in the local timezone. hours: "08:00-20:00", "closed", or null when unknown."""

    date: date
    hours: Optional[str]
    holiday: Optional[str] = None
    # "holiday hours", or "holiday, hours unknown" when only the weekday hours are known.
    note: Optional[str] = None
    open_now: Optional[bool] = None


class LocationRead(BaseModel):
    id: int
    name: str
    kind: str
    address: Optional[str]
    maps_url: Optional[str]
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_hours: Optional[dict[str, list[list[str]]]]
    opening_hours_text: str = ""
    notes: Optional[str]
    active: bool
    categories: list[LocationCategory] = Field(default_factory=list)
    today: Optional[LocationToday] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class LocationFilters:
    def __init__(
        self,
        kind: Annotated[Optional[str], Query()] = None,
        active: Annotated[Optional[bool], Query()] = None,
        category_id: Annotated[Optional[int], Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.kind = kind.strip().lower() if kind and kind.strip() else None
        if self.kind is not None and self.kind not in LOCATION_KINDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"kind must be one of {', '.join(LOCATION_KINDS)}",
            )
        self.active = active
        self.category_id = category_id
        self.limit = limit
        self.offset = offset

    def __eq__(self, other: object) -> bool:
        return isinstance(other, LocationFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"LocationFilters(kind={self.kind!r}, active={self.active!r}, category_id={self.category_id!r}, "
            f"limit={self.limit}, offset={self.offset})"
        )


# Total travel times across all locations; each one is ~10 tokens in a day plan.
MAX_TRAVEL_TIMES = 60


class LocationRef(BaseModel):
    id: int
    name: str
    kind: str

    model_config = {"from_attributes": True}


class LocationTravelTimeSet(BaseModel):
    """Minutes from the location in the path to `destination_id` by `mode`; saving the same route again updates it."""

    destination_id: int
    mode: str = Field(min_length=1, max_length=40)
    minutes: int = Field(ge=1, le=600)

    @field_validator("mode")
    @classmethod
    def _mode(cls, value: str) -> str:
        cleaned = " ".join(value.split()).lower()
        if not cleaned:
            raise ValueError("mode must not be blank")
        return cleaned


class LocationTravelTimeRead(BaseModel):
    id: int
    origin: LocationRef
    destination: LocationRef
    mode: str
    minutes: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
