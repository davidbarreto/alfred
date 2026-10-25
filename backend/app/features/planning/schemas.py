import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

_HH_MM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_WINDOW = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


def _check_hh_mm(value: str | None) -> str | None:
    if value is not None and not _HH_MM.match(value):
        raise ValueError(f"expected HH:MM, got {value!r}")
    return value


class PlanningSettingsRead(BaseModel):
    wake_time: str | None = None
    sleep_time: str | None = None
    work_target_minutes: int
    preferred_work_windows: list[str] = []
    work_tag: str
    office_tag: str
    office_days_per_week: int | None = None
    office_min_minutes: int | None = None


class PlanningSettingsUpdate(BaseModel):
    """Partial update: a field left out is untouched, an explicit null resets it to its default (unset)."""

    wake_time: str | None = None
    sleep_time: str | None = None
    work_target_minutes: int | None = Field(default=None, ge=0, le=1440)
    preferred_work_windows: list[str] | None = None
    work_tag: str | None = None
    office_tag: str | None = None
    office_days_per_week: int | None = Field(default=None, ge=1, le=7)
    office_min_minutes: int | None = Field(default=None, ge=0, le=1440)

    @field_validator("wake_time", "sleep_time")
    @classmethod
    def _hh_mm(cls, value: str | None) -> str | None:
        return _check_hh_mm(value)

    @field_validator("preferred_work_windows")
    @classmethod
    def _windows(cls, value: list[str] | None) -> list[str] | None:
        for window in value or []:
            match = _WINDOW.match(window)
            if not match or window.split("-")[1] <= window.split("-")[0]:
                raise ValueError(f"expected HH:MM-HH:MM with the end after the start, got {window!r}")
        return value

    @field_validator("work_tag", "office_tag")
    @classmethod
    def _tag(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("tag cannot be blank")
        return value.strip() if value is not None else None


class TimelineItem(BaseModel):
    kind: str
    title: str
    start: str
    end: str
    event_id: int | None = None
    routine_step_id: int | None = None
    availability: str | None = None
    presence: str | None = None
    location: str | None = None
    tags: list[str] | None = None
    notification_profile: str | None = None
    context: str | None = None
    checklist_note_id: int | None = None
    checklist_note_title: str | None = None


class RoutineBlock(BaseModel):
    routine: str
    routine_step_id: int
    title: str
    duration_minutes: int
    window: str
    fixed: bool | None = None
    context: str | None = None
    location: str | None = None
    checklist_note_id: int | None = None
    checklist_note_title: str | None = None


class AllDayItem(BaseModel):
    title: str
    event_id: int


class WorkSummary(BaseModel):
    target_minutes: int
    committed_minutes: int
    remaining_minutes: int
    preferred_windows: list[str] | None = None


class OfficeSummary(BaseModel):
    goal_per_week: int
    min_minutes: int
    planned_this_week: int
    days_left_in_week: int


class TaskItem(BaseModel):
    id: int
    title: str
    estimate_minutes: int | None = None
    context: str | None = None
    tags: list[str] | None = None
    priority: str | None = None
    urgency: str | None = None
    deadline: str | None = None
    available_from: str | None = None
    created_at: str | None = None


class RecurringTaskItem(TaskItem):
    due_dates: list[str] | None = None
    flexible: bool | None = None


class StudyItemRef(BaseModel):
    item_id: int
    description: str


class StudyPlanSummary(BaseModel):
    plan_id: int
    title: str
    goal: str
    priority: str
    tags: list[str] | None = None
    open_items: list[StudyItemRef]


class LanguageProgress(BaseModel):
    track: str
    daily_quota: int
    done_today: int
    quota_met: bool


class StudySection(BaseModel):
    plans: list[StudyPlanSummary] = []
    language: list[LanguageProgress] = []


class SuggestedRun(BaseModel):
    estimate_minutes: int
    context: str


class ShoppingSection(BaseModel):
    pending_items: int
    due_recurring: int
    suggested_run: SuggestedRun


class DayRead(BaseModel):
    date: str
    timeline: list[TimelineItem] = []
    routine_blocks: list[RoutineBlock] = []
    all_day: list[AllDayItem] = []
    work: WorkSummary


class DayPlanRead(BaseModel):
    """One day's fields sit at the top level when a single day is requested, else under `days`."""

    date: str
    timezone: str
    preferences: dict[str, Any]
    work: WorkSummary | None = None
    office: OfficeSummary | None = None
    timeline: list[TimelineItem] | None = None
    routine_blocks: list[RoutineBlock] | None = None
    all_day: list[AllDayItem] | None = None
    days: list[DayRead] | None = None
    overdue_tasks: list[TaskItem] = []
    due_tasks: list[TaskItem] = []
    recurring_tasks: list[RecurringTaskItem] = []
    backlog_tasks: list[TaskItem] = []
    study: StudySection | None = None
    shopping: ShoppingSection | None = None
    activity_suggestions: list[dict[str, Any]] | None = None
    saved_plan: list[dict[str, Any]] | None = None
    warnings: list[str] = []
