from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import Query
from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.organizer.tasks.schemas import TaskContext


def _check_range(min_minutes: int | None, max_minutes: int | None) -> None:
    if min_minutes is not None and max_minutes is not None and max_minutes < min_minutes:
        raise ValueError("max_minutes must not be less than min_minutes")


class ActivityBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    min_minutes: int | None = Field(default=None, gt=0)
    max_minutes: int | None = Field(default=None, gt=0)
    context: TaskContext | None = None
    target_per_week: int | None = Field(default=None, gt=0)
    tags: list[str] = []

    @model_validator(mode="after")
    def _min_max(self) -> "ActivityBase":
        _check_range(self.min_minutes, self.max_minutes)
        return self


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    min_minutes: int | None = Field(default=None, gt=0)
    max_minutes: int | None = Field(default=None, gt=0)
    context: TaskContext | None = None
    target_per_week: int | None = Field(default=None, gt=0)
    tags: list[str] | None = None

    @model_validator(mode="after")
    def _title_not_null(self) -> "ActivityUpdate":
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        _check_range(self.min_minutes, self.max_minutes)
        return self


class ActivityRead(ActivityBase):
    id: int
    archived_at: datetime | None = None
    last_done_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]


class ActivityLogCreate(BaseModel):
    done_at: datetime | None = Field(default=None, description="When it was done; defaults to now (use it to catch up)")
    minutes: int | None = Field(default=None, gt=0)
    note: str | None = None


class ActivityLogRead(BaseModel):
    id: int
    activity_id: int
    done_at: datetime
    minutes: int | None = None
    note: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityFilters:
    def __init__(
        self,
        include_archived: Annotated[bool, Query()] = False,
        tag: Annotated[Optional[str], Query(description="Only activities with this tag")] = None,
        q: Annotated[Optional[str], Query(description="Case-insensitive substring match on title")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
    ) -> None:
        self.include_archived = include_archived
        self.tag = tag
        self.q = q
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ActivityFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"ActivityFilters(include_archived={self.include_archived!r}, tag={self.tag!r}, "
            f"q={self.q!r}, limit={self.limit})"
        )


class WeekStat(BaseModel):
    week_start: date
    count: int
    minutes: int


class ActivityStat(BaseModel):
    activity_id: int
    title: str
    count: int
    minutes: int


class TagStat(BaseModel):
    tag: str
    count: int
    minutes: int


class ActivityStats(BaseModel):
    weeks: list[WeekStat]
    by_activity: list[ActivityStat]
    by_tag: list[TagStat]
    total_count: int
    total_minutes: int


class ActivitySuggestion(BaseModel):
    id: int
    title: str
    min_minutes: int | None = None
    max_minutes: int | None = None
    context: str | None = None
    tags: list[str] | None = None
    days_since_last_done: int | None = None
    target_per_week: int | None = None
    done_this_week: int | None = None
