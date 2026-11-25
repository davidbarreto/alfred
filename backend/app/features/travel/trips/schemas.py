from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.features.location.cities.schemas import CityRef
from app.features.travel.constants import TripStatusFilter
from app.features.travel.legs.schemas import LegRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.schemas import normalize_tags
from app.features.travel.visits.schemas import VisitRead
from app.features.travel.trips.trip_cities import TripCity
from app.features.travel.trips.timeline import TimelineItem, TripWarning
from app.shared.utils.links import photo_album_label
from app.shared.utils.timezone import local_today

TripStatus = Literal["upcoming", "ongoing", "past"]


def clean_album_url(value: str | None) -> str | None:
    """A trip's photo album link: http or https only; blank clears it."""
    if value is None or not value.strip():
        return None
    value = value.strip()
    if not value.lower().startswith(("http://", "https://")):
        raise ValueError("photo_album_url must start with http:// or https://")
    return value


def trip_status(start: date, end: date, today: date) -> TripStatus:
    if end < today:
        return "past"
    return "upcoming" if start > today else "ongoing"


class TripCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: date
    end_date: date
    travelers: str | None = None
    preferences: str | None = None
    checklist_note_id: int | None = None
    notes: str | None = None
    default_tag_names: str | None = None
    tags: list[str] = Field(default_factory=list)
    # The trip's shared photo album; blank or null means none.
    photo_album_url: str | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return normalize_tags(tags) or []

    @field_validator("photo_album_url")
    @classmethod
    def _album(cls, value: str | None) -> str | None:
        return clean_album_url(value)

    @model_validator(mode="after")
    def _dates_in_order(self) -> "TripCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        return self


class TripUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    travelers: str | None = None
    preferences: str | None = None
    checklist_note_id: int | None = None
    notes: str | None = None
    default_tag_names: str | None = None
    tags: list[str] | None = None
    # The trip's own home and airport times; null makes the trip follow the travel settings again.
    home_city_id: int | None = None
    home_address: str | None = Field(default=None, max_length=300)
    airport_buffer_min: int | None = Field(default=None, ge=0, le=600)
    home_to_airport_min: int | None = Field(default=None, ge=0, le=600)
    # Blank or null clears it.
    photo_album_url: str | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        return normalize_tags(tags)

    @field_validator("photo_album_url")
    @classmethod
    def _album(cls, value: str | None) -> str | None:
        return clean_album_url(value)


class TripRead(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    travelers: str | None
    preferences: str | None
    checklist_note_id: int | None
    notes: str | None
    default_tag_names: str | None
    home_city_id: int | None = None
    home_address: str | None = None
    airport_buffer_min: int | None = None
    home_to_airport_min: int | None = None
    photo_album_url: str | None = None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def photo_album_label(self) -> str | None:
        """"Google Photos", "iCloud", "Flickr", "OneDrive" or "Photo album", from the link's domain."""
        return photo_album_label(self.photo_album_url)

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value):
        return [getattr(tag, "name", tag) for tag in value]

    @computed_field
    @property
    def status(self) -> TripStatus:
        return trip_status(self.start_date, self.end_date, local_today())


class TripListItem(TripRead):
    """A trip in the list: also the cities and countries of the places it stays at or visits."""

    cities: list[str] = []
    countries: list[str] = []


class TripLocations(BaseModel):
    """Every city and country of a place a trip stays at or visits, for the list filters' autocomplete."""

    cities: list[str]
    countries: list[str]


class TripFilters:
    def __init__(
        self,
        status: Annotated[
            TripStatusFilter, Query(description="current = upcoming + ongoing (default)")
        ] = "current",
        tag: Annotated[list[str] | None, Query(description="Trip must carry every given tag")] = None,
        q: Annotated[str | None, Query(description="Substring of the trip name")] = None,
        date_from: Annotated[date | None, Query(description="Trips ending on or after this date")] = None,
        date_to: Annotated[date | None, Query(description="Trips starting on or before this date")] = None,
        city: Annotated[str | None, Query(description="Trips with a stay or visit in a place in this city")] = None,
        country: Annotated[str | None, Query(description="Trips with a stay or visit in a place in this country")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.status = status
        self.tag = tag
        self.q = q
        self.date_from = date_from
        self.date_to = date_to
        self.city = city
        self.country = country
        self.limit = limit
        self.offset = offset


class IdeaGroup(BaseModel):
    """Undated planned visits and wishlist places in one city of the trip."""

    city: str
    visits: list[VisitRead]


class TripHome(BaseModel):
    """Where the trip starts from: its own values, else the travel settings'."""

    city: CityRef | None = None
    address: str | None = None
    airport_buffer_min: int
    home_to_airport_min: int
    # The trip has a value of its own ("home for this trip").
    from_trip: bool = False


class TripDetail(TripRead):
    legs: list[LegRead]
    stays: list[StayRead]
    timeline: list[TimelineItem]
    leave_home_at: datetime | None = None
    visits: list[VisitRead] = []
    # Planned and missed visits of an ended trip are hidden unless asked for; this says how many.
    hidden_visit_count: int = 0
    warnings: list[TripWarning]
    # Planned visits with no day yet (the trip's own and the wishlist's), by stay city; empty once the trip is over.
    ideas: list[IdeaGroup] = []
    # Where the trip went (stays, visits, leg ends), in order of first appearance, and the leg ends with no city.
    cities: list[TripCity] = []
    home: TripHome | None = None
    unmatched_leg_ends: int = 0
