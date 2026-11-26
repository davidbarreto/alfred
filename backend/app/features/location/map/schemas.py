"""Compact rows for the Places map: countries (shapes by ISO code), cities (markers) and places (pins)."""
from typing import Annotated, Optional

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, computed_field

from app.features.location.places.constants import PlaceKind
from app.shared.utils.links import place_maps_url


class MapFilters:
    """At most one of country_id and city_id; neither is the whole world."""

    def __init__(
        self,
        country_id: Annotated[Optional[int], Query(description="Only this country, its cities and their places")] = None,
        city_id: Annotated[Optional[int], Query(description="Only this city (and its country) and its places")] = None,
    ) -> None:
        if country_id is not None and city_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pass country_id or city_id, not both",
            )
        self.country_id = country_id
        self.city_id = city_id


class MapCountry(BaseModel):
    id: int
    name: str
    # ISO alpha-2: what matches the country to its shape. Null = it can't be drawn ("not on the map").
    code: Optional[str]
    city_count: int


class MapCity(BaseModel):
    id: int
    name: str
    country_id: int
    latitude: float
    longitude: float
    home: bool = False


class MapPlace(BaseModel):
    id: int
    name: str
    kind: PlaceKind
    city_id: int
    city_name: str
    latitude: float
    longitude: float
    maps_url: Optional[str] = None

    @computed_field
    @property
    def maps_link(self) -> str:
        return place_maps_url(self.name, self.city_name, self.maps_url, self.latitude, self.longitude)


class PlacesMap(BaseModel):
    countries: list[MapCountry]
    # Only cities and places with coordinates; the counts say how many were left out.
    cities: list[MapCity]
    places: list[MapPlace]
    cities_without_coordinates: int
    places_without_coordinates: int
