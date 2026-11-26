from datetime import date, datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, Field, computed_field, model_validator

from app.features.location.cities.schemas import CityRef


def check_period(from_date: date | None, to_date: date | None, born: bool) -> None:
    """Only the birth row may start "since birth", and a period ends after it starts."""
    if from_date is None and not born:
        raise ValueError("from_date is required unless this is the birth row")
    if from_date is not None and to_date is not None and to_date <= from_date:
        raise ValueError("to_date must be after from_date")


class ResidenceCreate(BaseModel):
    city_id: int
    # Null only on the birth row: since birth.
    from_date: date | None = None
    # Null: still living there. The moving day itself belongs to the next row.
    to_date: date | None = None
    born: bool = False
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _period(self) -> "ResidenceCreate":
        check_period(self.from_date, self.to_date, self.born)
        return self


class ResidenceUpdate(BaseModel):
    """Only the fields sent change; `from_date`, `to_date` and `notes` may be set to null. Checked as a whole after merging."""

    city_id: int | None = None
    from_date: date | None = None
    to_date: date | None = None
    born: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ResidenceRead(BaseModel):
    id: int
    city: CityRef
    from_date: date | None
    to_date: date | None
    born: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def current(self) -> bool:
        """Still living there."""
        return self.to_date is None


class ResidenceFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.limit = limit
        self.offset = offset
