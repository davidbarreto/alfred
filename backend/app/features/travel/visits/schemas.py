from datetime import date, datetime, time
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, model_validator

from app.features.travel.constants import PlaceKind, VisitStatus
from app.features.travel.links import place_maps_url


class VisitCreate(BaseModel):
    place_id: int
    trip_id: int | None = None
    status: VisitStatus = "planned"
    visit_date: date | None = None
    visit_time: time | None = None
    notes: str | None = None
    grade: int | None = Field(default=None, ge=1, le=5)

    @model_validator(mode="after")
    def _grade_needs_a_done_visit(self) -> "VisitCreate":
        if self.grade is not None and self.status != "visited":
            raise ValueError("Only a visited visit can be graded")
        return self


class VisitUpdate(BaseModel):
    place_id: int | None = None
    trip_id: int | None = None
    status: VisitStatus | None = None
    visit_date: date | None = None
    visit_time: time | None = None
    notes: str | None = None
    grade: int | None = Field(default=None, ge=1, le=5)


class VisitPlace(BaseModel):
    """The slice of a place a visit row needs."""

    id: int
    kind: PlaceKind
    name: str
    city: str | None
    country: str | None = None
    maps_url: str | None
    lat: float | None
    lng: float | None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def maps_link(self) -> str:
        return place_maps_url(self.name, self.city, self.maps_url, self.lat, self.lng)


class VisitRead(BaseModel):
    id: int
    place_id: int
    place: VisitPlace
    trip_id: int | None
    trip_name: str | None
    status: VisitStatus
    visit_date: date | None
    visit_time: time | None
    notes: str | None
    grade: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VisitFilters:
    def __init__(
        self,
        trip_id: Annotated[int | None, Query()] = None,
        place_id: Annotated[int | None, Query()] = None,
        status: Annotated[VisitStatus | None, Query()] = None,
        date_from: Annotated[date | None, Query()] = None,
        date_to: Annotated[date | None, Query()] = None,
        no_trip: Annotated[bool, Query(description="Only visits that belong to no trip")] = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.trip_id = trip_id
        self.place_id = place_id
        self.status = status
        self.date_from = date_from
        self.date_to = date_to
        self.no_trip = no_trip
        self.limit = limit
        self.offset = offset
