from datetime import date, datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, field_validator, model_validator


class CountryRef(BaseModel):
    id: int
    name: str
    code: str | None = None

    model_config = {"from_attributes": True}


class CityRef(BaseModel):
    id: int
    name: str
    country: CountryRef

    model_config = {"from_attributes": True}


class CityRead(CityRef):
    created_at: datetime
    updated_at: datetime


class CityCreate(BaseModel):
    """Exactly one of `country_id` (an existing country) or `country` (a name, created when new)."""

    name: str = Field(min_length=1, max_length=100)
    country_id: int | None = None
    country: str | None = Field(default=None, min_length=1, max_length=100)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)

    @model_validator(mode="after")
    def _one_country(self) -> "CityCreate":
        if (self.country_id is None) == (self.country is None):
            raise ValueError("Send exactly one of country_id or country")
        return self


class CityFilters:
    def __init__(
        self,
        country_id: Annotated[int | None, Query()] = None,
        q: Annotated[str | None, Query(description="Case-insensitive substring of the city name")] = None,
    ):
        self.country_id = country_id
        self.q = q


class CityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    country_id: int | None = None


class CountryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # ISO 3166-1 alpha-2; null clears it.
    code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.isalpha() or not value.isascii():
            raise ValueError("code must be two letters")
        return value.upper()


class LocationTrip(BaseModel):
    """A trip that touches a city or country (a stay, a visit or a leg end there)."""

    id: int
    name: str
    start_date: date
    end_date: date

    model_config = {"from_attributes": True}


class CityPlace(BaseModel):
    id: int
    name: str
    kind: str
    grade: float | None = None


class CityDetail(CityRead):
    # Derived, never stored: the mean of the grades of this city's graded places.
    grade: float | None = None
    grade_count: int = 0
    place_count: int = 0
    # The first five by name; the places page (`?city_id=`) lists them all.
    places: list[CityPlace] = []
    # Newest first.
    trips: list[LocationTrip] = []


class CountryCity(BaseModel):
    id: int
    name: str
    place_count: int = 0
    grade: float | None = None


class CountryDetail(CountryRef):
    created_at: datetime
    updated_at: datetime
    # The mean of the grades of this country's graded cities.
    grade: float | None = None
    grade_count: int = 0
    cities: list[CountryCity] = []
    trips: list[LocationTrip] = []
