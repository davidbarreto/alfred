from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import Query
from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.metrics.series.schemas import SeriesKind, normalize_series_name
from app.features.metrics.tags.schemas import normalize_tags

EntryStatus = Literal["open", "closed", "discarded"]
EntrySource = Literal["telegram", "shortcut", "portal", "mcp"]


class _Location(BaseModel):
    """Optional device coordinates; latitude and longitude come together or not at all."""

    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _lat_lon_together(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("lat and lon must be provided together")
        return self


class _Tagged(BaseModel):
    @field_validator("tags", check_fields=False)
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return normalize_tags(value)


class MetricStart(_Location, _Tagged):
    series: str
    tags: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("series")
    @classmethod
    def _clean_series(cls, value: str) -> str:
        return normalize_series_name(value)


class MetricStop(_Location):
    series: str | None = None
    ago_s: int | None = Field(default=None, ge=0)

    @field_validator("series")
    @classmethod
    def _clean_series(cls, value: str | None) -> str | None:
        return normalize_series_name(value) if value is not None else None


class MetricLog(_Location, _Tagged):
    series: str
    value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=20)
    tags: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("series")
    @classmethod
    def _clean_series(cls, value: str) -> str:
        return normalize_series_name(value)

    @field_validator("unit")
    @classmethod
    def _clean_unit(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class MetricEntryCreate(_Tagged):
    """Manual entry (portal): the series must already exist."""

    series: str
    started_at: datetime
    ended_at: datetime | None = None
    value: float | None = Field(default=None, allow_inf_nan=False)
    tags: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("series")
    @classmethod
    def _clean_series(cls, value: str) -> str:
        return normalize_series_name(value)


class MetricEntryUpdate(_Tagged):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    value: float | None = Field(default=None, allow_inf_nan=False)
    tags: list[str] | None = None
    note: str | None = None


class MetricEntryRead(BaseModel):
    id: int
    series_id: int
    series_name: str
    series_kind: SeriesKind
    started_at: datetime
    ended_at: datetime | None
    duration_s: int | None
    value: float | None
    status: EntryStatus
    is_stale: bool = False
    source: EntrySource
    start_lat: float | None
    start_lon: float | None
    start_accuracy_m: float | None
    end_lat: float | None
    end_lon: float | None
    end_accuracy_m: float | None
    context: dict[str, Any] | None
    note: str | None
    tags: list[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, value: Any) -> Any:
        return [getattr(tag, "name", tag) for tag in value]


class MetricActionResult(BaseModel):
    message: str
    entry: MetricEntryRead
    series_created: bool = False
    discarded_entry_id: int | None = None


class MetricEntryFilters:
    def __init__(
        self,
        series: Annotated[str | None, Query()] = None,
        tag: Annotated[str | None, Query()] = None,
        status: Annotated[EntryStatus | None, Query()] = None,
        since: Annotated[datetime | None, Query()] = None,
        until: Annotated[datetime | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        self.series = series
        self.tag = tag
        self.status = status
        self.since = since
        self.until = until
        self.limit = limit
        self.offset = offset
