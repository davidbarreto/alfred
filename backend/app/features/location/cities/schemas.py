from datetime import datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, model_validator

from app.features.location.countries.schemas import CountryRef


class CityRef(BaseModel):
    id: int
    name: str
    country: CountryRef

    model_config = {"from_attributes": True}


class CityRead(CityRef):
    default_tag_names: str | None = None
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
    # Comma-separated finance tag names; blank or null clears them.
    default_tag_names: str | None = None
