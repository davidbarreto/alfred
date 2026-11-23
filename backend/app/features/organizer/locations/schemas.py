from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

# Suggested in the portal; kind stays free text.
SUGGESTED_KINDS = ("home", "work", "school", "gym", "supermarket", "pharmacy", "bakery", "market", "other")
DEFAULT_KIND = "other"


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("name must not be blank")
    if len(cleaned) > 100:
        raise ValueError("name must be at most 100 characters")
    return cleaned


def _clean_kind(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split()).lower()
    if not cleaned:
        raise ValueError("kind must not be blank")
    if len(cleaned) > 30:
        raise ValueError("kind must be at most 30 characters")
    return cleaned


def _blank_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip() or None


class LocationCreate(BaseModel):
    name: str
    kind: str = DEFAULT_KIND
    address: Optional[str] = None
    maps_url: Optional[str] = None
    # Text ("mon-fri 08:00-20:00; sun closed; holidays closed") or the stored object; the service parses it.
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: bool = True
    category_ids: list[int] = Field(default_factory=list)

    _name = field_validator("name")(_clean_name)
    _kind = field_validator("kind")(_clean_kind)
    _text = field_validator("address", "maps_url", "notes")(_blank_to_none)


class LocationUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    address: Optional[str] = None
    maps_url: Optional[str] = None
    # A blank text or null clears the hours (unknown again).
    opening_hours: Optional[str | dict[str, Any]] = None
    notes: Optional[str] = None
    active: Optional[bool] = None
    # Replaces the whole list when given.
    category_ids: Optional[list[int]] = None

    _name = field_validator("name")(_clean_name)
    _kind = field_validator("kind")(_clean_kind)
    _text = field_validator("address", "maps_url", "notes")(_blank_to_none)


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
        self.kind = kind.strip().lower() if kind else None
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
