from datetime import datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.features.travel.cities.schemas import CityRef
from app.features.travel.constants import PlaceKind, VisitStatus
from app.shared.utils.links import place_maps_url
from app.features.travel.tags.schemas import normalize_tags


class PlaceCreate(BaseModel):
    """The city is `city_id`, or `city` + `country` (+ `country_code`), found or created by name."""

    kind: PlaceKind
    name: str = Field(min_length=1, max_length=200)
    city_id: int | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
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

    @model_validator(mode="after")
    def _one_city_form(self) -> "PlaceCreate":
        named = self.city is not None and self.country is not None
        if (self.city_id is not None) == named or (self.city is None) != (self.country is None):
            raise ValueError("Send city_id, or city and country")
        return self


class PlaceUpdate(BaseModel):
    kind: PlaceKind | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    # Either form re-points the place; a lone city or country keeps the other from the place's current city.
    city_id: int | None = None
    city: str | None = Field(default=None, min_length=1, max_length=100)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
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

    @model_validator(mode="after")
    def _one_city_form(self) -> "PlaceUpdate":
        if self.city_id is not None and (self.city is not None or self.country is not None):
            raise ValueError("Send city_id, or city and country, not both")
        return self


class PlaceRead(BaseModel):
    id: int
    kind: PlaceKind
    name: str
    city: CityRef
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
        return place_maps_url(self.name, self.city.name, self.maps_url, self.lat, self.lng)


class PlaceFilters:
    def __init__(
        self,
        q: Annotated[str | None, Query(description="Substring of name, city, country or address")] = None,
        kind: Annotated[PlaceKind | None, Query()] = None,
        city: Annotated[str | None, Query()] = None,
        country: Annotated[str | None, Query()] = None,
        city_id: Annotated[int | None, Query()] = None,
        country_id: Annotated[int | None, Query()] = None,
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
        self.city_id = city_id
        self.country_id = country_id
        self.tag = tag
        self.min_grade = min_grade
        self.ungraded = ungraded
        self.status = status
        self.no_trip = no_trip
        self.limit = limit
        self.offset = offset


class PlaceLocations(BaseModel):
    """Every city and country of any place, for the places filters' autocomplete."""

    cities: list[str]
    countries: list[str]
