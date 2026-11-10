from datetime import datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, field_validator

from app.features.travel.constants import PlaceKind, VisitStatus
from app.features.travel.links import place_maps_url
from app.features.travel.tags.schemas import normalize_tags


class PlaceCreate(BaseModel):
    kind: PlaceKind
    name: str = Field(min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    maps_url: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = None
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        return normalize_tags(tags) or []


class PlaceUpdate(BaseModel):
    kind: PlaceKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, max_length=100)
    maps_url: str | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = None
    notes: str | None = None
    tags: list[str] | None = None

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str] | None) -> list[str] | None:
        return normalize_tags(tags)


class PlaceRead(BaseModel):
    id: int
    kind: PlaceKind
    name: str
    city: str | None
    country: str | None
    maps_url: str | None
    lat: float | None
    lng: float | None
    address: str | None
    notes: str | None
    tags: list[str] = []
    # Derived, never stored: the average over this place's graded visits and stays.
    grade: float | None = None
    grade_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value):
        return [getattr(tag, "name", tag) for tag in value]

    @computed_field
    @property
    def maps_link(self) -> str:
        return place_maps_url(self.name, self.city, self.maps_url, self.lat, self.lng)


class PlaceFilters:
    def __init__(
        self,
        q: Annotated[str | None, Query(description="Substring of name, city, country or address")] = None,
        kind: Annotated[PlaceKind | None, Query()] = None,
        city: Annotated[str | None, Query()] = None,
        country: Annotated[str | None, Query()] = None,
        tag: Annotated[list[str] | None, Query(description="Place must carry every given tag")] = None,
        min_grade: Annotated[int | None, Query(ge=1, le=5, description="Minimum derived grade")] = None,
        ungraded: Annotated[bool, Query(description="Only places with no grade yet")] = False,
        status: Annotated[VisitStatus | None, Query(description="Has a visit with this status")] = None,
        no_trip: Annotated[bool, Query(description="Only places in no trip (no visit or stay carries a trip)")] = False,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.q = q
        self.kind = kind
        self.city = city
        self.country = country
        self.tag = tag
        self.min_grade = min_grade
        self.ungraded = ungraded
        self.status = status
        self.no_trip = no_trip
        self.limit = limit
        self.offset = offset
