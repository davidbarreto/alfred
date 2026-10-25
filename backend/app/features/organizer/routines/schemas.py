from datetime import date, datetime, time
from typing import Annotated, Literal, Optional

from fastapi import Query
from pydantic import BaseModel, Field, model_validator

from app.features.organizer.tasks.schemas import TaskContext

StepAnchor = Literal["start", "end"]


class RoutineStepBase(BaseModel):
    title: str
    duration_minutes: int = Field(default=0, ge=0)
    anchor: StepAnchor | None = None
    offset_minutes: int | None = None
    window_start: time | None = None
    window_end: time | None = None
    context: TaskContext | None = None
    location: str | None = None
    checklist_note_id: int | None = None

    @model_validator(mode="after")
    def _exactly_one_timing_form(self) -> "RoutineStepBase":
        relative = (self.anchor is not None, self.offset_minutes is not None)
        window = (self.window_start is not None, self.window_end is not None)
        if any(relative) and not all(relative):
            raise ValueError("anchor and offset_minutes must be set together")
        if any(window) and not all(window):
            raise ValueError("window_start and window_end must be set together")
        if all(relative) == all(window):
            raise ValueError(
                "set exactly one timing form: anchor + offset_minutes (relative to an event) "
                "or window_start + window_end (scheduled routines)"
            )
        if self.window_start is not None and self.window_end is not None and self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        return self


class RoutineStepCreate(RoutineStepBase):
    position: int | None = Field(default=None, ge=0)


class RoutineStepUpdate(BaseModel):
    title: str | None = None
    duration_minutes: int | None = Field(default=None, ge=0)
    anchor: StepAnchor | None = None
    offset_minutes: int | None = None
    window_start: time | None = None
    window_end: time | None = None
    context: TaskContext | None = None
    location: str | None = None
    checklist_note_id: int | None = None
    position: int | None = Field(default=None, ge=0)


class RoutineStepRead(RoutineStepBase):
    id: int
    routine_id: int
    position: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChecklistNote(BaseModel):
    id: int
    title: str
    content: str


class RoutineStepDetail(RoutineStepRead):
    checklist_note: ChecklistNote | None = None


class RoutineBase(BaseModel):
    name: str
    description: str | None = None
    active: bool = True
    recurrence_rule: str | None = None
    starts_on: date | None = None

    @model_validator(mode="after")
    def _rule_and_start_together(self) -> "RoutineBase":
        if (self.recurrence_rule is None) != (self.starts_on is None):
            raise ValueError("recurrence_rule and starts_on must be set together (or both left empty)")
        return self


class RoutineCreate(RoutineBase):
    pass


class RoutineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    active: bool | None = None
    recurrence_rule: str | None = None
    starts_on: date | None = None

    @model_validator(mode="after")
    def _not_null_columns(self) -> "RoutineUpdate":
        for field in ("name", "active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class RoutineRead(RoutineBase):
    id: int
    steps: list[RoutineStepRead] = []
    event_ids: list[int] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoutineDetail(RoutineRead):
    steps: list[RoutineStepDetail] = []


class RoutineFilters:
    def __init__(
        self,
        active: Annotated[Optional[bool], Query(description="Only active (true) or inactive (false) routines")] = None,
    ) -> None:
        self.active = active

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RoutineFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"RoutineFilters(active={self.active!r})"
