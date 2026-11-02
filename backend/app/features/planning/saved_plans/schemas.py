import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

BLOCK_KINDS = (
    "event", "task", "study_item", "activity", "routine_step", "routine_block", "work", "transport", "meal", "break", "other",
)
BlockKind = Literal[
    "event", "task", "study_item", "activity", "routine_step", "routine_block", "work", "transport", "meal", "break", "other"
]
# Kinds that point at a row; work/transport/meal/break/other blocks are free-form and carry no ref_id.
REF_KINDS = ("event", "task", "study_item", "activity", "routine_step", "routine_block")

_HH_MM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

MAX_SAVE_DAYS = 31
MAX_RANGE_DAYS = 62


class PlanBlock(BaseModel):
    """One block of a saved day. Datetimes must carry their UTC offset."""

    start: datetime
    end: datetime
    kind: BlockKind
    ref_id: int | None = None
    title: str = Field(min_length=1)
    note: str | None = None

    @field_validator("start", "end")
    @classmethod
    def _needs_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("datetime must include a UTC offset, e.g. 2026-10-21T18:00:00+01:00")
        return value

    @model_validator(mode="after")
    def _ordered(self) -> "PlanBlock":
        if self.end < self.start:
            raise ValueError("end must not be before start")
        if self.kind not in REF_KINDS and self.ref_id is not None:
            raise ValueError(f"a '{self.kind}' block cannot have a ref_id")
        return self


class DayPlanSave(BaseModel):
    date: date
    items: list[PlanBlock]
    notes: str | None = None


class DayPlansSave(BaseModel):
    days: list[DayPlanSave] = Field(min_length=1, max_length=MAX_SAVE_DAYS)


class DayPlanEdit(BaseModel):
    """Replace the blocks of one day that start in [replace_from, replace_to) (local HH:MM) with `items`."""

    date: date
    replace_from: str
    replace_to: str
    items: list[PlanBlock] = []
    notes: str | None = None

    @field_validator("replace_from", "replace_to")
    @classmethod
    def _hh_mm(cls, value: str) -> str:
        if not _HH_MM.match(value):
            raise ValueError(f"expected HH:MM, got {value!r}")
        return value

    @model_validator(mode="after")
    def _window_ordered(self) -> "DayPlanEdit":
        if self.replace_to <= self.replace_from:
            raise ValueError("replace_to must be after replace_from")
        return self


class DayPlansEdit(BaseModel):
    days: list[DayPlanEdit] = Field(min_length=1, max_length=MAX_SAVE_DAYS)


class SavedPlanSummary(BaseModel):
    """What a save or an edit returns: enough to know it landed, without echoing the blocks back."""

    id: int
    plan_date: date
    version: int
    blocks: int


class PlanBlockRead(BaseModel):
    start: str
    end: str
    kind: str
    ref_id: int | None = None
    title: str
    note: str | None = None
    missed: bool | None = None
    missed_at: str | None = None
    done: bool | None = None
    done_at: str | None = None


class ReviewItem(BaseModel):
    kind: str
    ref_id: int | None = None
    title: str
    planned: int
    done: int
    missed: int
    unmarked: int
    upcoming: int
    missed_dates: list[str] = []


class ReviewRead(BaseModel):
    from_date: date
    to_date: date
    items: list[ReviewItem]
    planned: int
    done: int
    missed: int
    unmarked: int
    upcoming: int


class SavedDayPlanRead(BaseModel):
    id: int
    plan_date: date
    version: int
    items: list[PlanBlockRead]
    notes: str | None = None
    source: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}
