from datetime import datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field

from app.features.travel.constants import PlaceKind
from app.features.travel.links import place_maps_url


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

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
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.q = q
        self.kind = kind
        self.city = city
        self.country = country
        self.limit = limit
        self.offset = offset
