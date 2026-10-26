from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

BLOCK_KINDS = ("event", "task", "study_item", "activity", "routine_step", "routine_block", "meal", "break", "other")
BlockKind = Literal["event", "task", "study_item", "activity", "routine_step", "routine_block", "meal", "break", "other"]
# Kinds that point at a row; meal/break/other blocks are free-form and carry no ref_id.
REF_KINDS = ("event", "task", "study_item", "activity", "routine_step", "routine_block")

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


class PlanBlockRead(BaseModel):
    start: str
    end: str
    kind: str
    ref_id: int | None = None
    title: str
    note: str | None = None


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
