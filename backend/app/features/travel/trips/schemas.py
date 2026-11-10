from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.features.travel.constants import TripStatusFilter
from app.features.travel.legs.schemas import LegRead
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.schemas import normalize_tags
from app.features.travel.visits.schemas import VisitRead
from app.features.travel.trips.timeline import TimelineItem, TripWarning
from app.shared.timezone import local_today

TripStatus = Literal["upcoming", "ongoing", "past"]


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

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return normalize_tags(tags) or []

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

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        return normalize_tags(tags)


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
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value):
        return [getattr(tag, "name", tag) for tag in value]

    @computed_field
    @property
    def status(self) -> TripStatus:
        return trip_status(self.start_date, self.end_date, local_today())


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


class TripDetail(TripRead):
    legs: list[LegRead]
    stays: list[StayRead]
    timeline: list[TimelineItem]
    leave_home_at: datetime | None = None
    visits: list[VisitRead] = []
    # Planned and missed visits of an ended trip are hidden unless asked for; this says how many.
    hidden_visit_count: int = 0
    warnings: list[TripWarning]
