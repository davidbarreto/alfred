import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

SeriesKind = Literal["duration", "value", "count"]

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def normalize_series_name(name: str) -> str:
    """Lowercase slug: trimmed, whitespace collapsed to '-'. Raises ValueError when not a valid slug."""
    cleaned = re.sub(r"\s+", "-", name.strip().lower())
    if not _NAME_RE.match(cleaned):
        raise ValueError("series name must be 1-64 chars: letters, digits, '-' or '_' (starting with a letter or digit)")
    return cleaned


class MetricSeriesCreate(BaseModel):
    name: str
    kind: SeriesKind
    unit: str | None = Field(default=None, max_length=20)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return normalize_series_name(value)


class MetricSeriesUpdate(BaseModel):
    name: str | None = None
    unit: str | None = Field(default=None, max_length=20)
    description: str | None = None
    is_archived: bool | None = None

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str | None) -> str | None:
        return normalize_series_name(value) if value is not None else None


class MetricSeriesMerge(BaseModel):
    into: str

    @field_validator("into")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return normalize_series_name(value)


class MetricSeriesRead(BaseModel):
    id: int
    name: str
    kind: SeriesKind
    unit: str | None
    description: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MetricSeriesSummary(MetricSeriesRead):
    entry_count: int = 0
