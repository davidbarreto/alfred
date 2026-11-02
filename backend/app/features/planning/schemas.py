import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.organizer.activities.schemas import ActivitySuggestion

_HH_MM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_WINDOW = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_WORKDAYS = WEEKDAYS[:5]
CONVENTIONS_MAX_LENGTH = 2000
MAX_TRAVEL_TIMES = 20


HOME = "home"


class TravelTime(BaseModel):
    """Minutes door to door between two places by one mode, e.g. home to office by metro: 50.

    Two-way: the same minutes apply the other way round unless the reverse trip is listed too.
    `origin` defaults to home; `place` is the destination.
    """

    origin: str = Field(default=HOME, min_length=1, max_length=60)
    place: str = Field(min_length=1, max_length=60)
    mode: str = Field(min_length=1, max_length=40)
    minutes: int = Field(ge=1, le=600)

    @field_validator("origin", "place", "mode")
    @classmethod
    def _normalised(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("cannot be blank")
        return value

    @model_validator(mode="after")
    def _distinct_places(self) -> "TravelTime":
        if self.origin == self.place:
            raise ValueError(f"{self.place} cannot be travelled to from itself")
        return self


def _unique_travel_times(value: list[TravelTime] | None) -> list[TravelTime] | None:
    seen = set()
    for entry in value or []:
        key = (entry.origin, entry.place, entry.mode)
        if key in seen:
            raise ValueError(f"{entry.origin} to {entry.place} by {entry.mode} is listed twice")
        seen.add(key)
    return value


def parse_travel_times(text: str) -> list[dict[str, Any]]:
    """Parse "office:metro=50,car=20;office>school:walk=10" into [{origin, place, mode, minutes}, ...].

    A group is `[origin>]place:mode=minutes[,mode=minutes]`; without an origin the trip starts at home.
    """
    entries = []
    for group in filter(None, (part.strip() for part in text.split(";"))):
        route, separator, modes = group.partition(":")
        if not separator or not modes.strip():
            raise ValueError(f"expected [origin>]place:mode=minutes[,mode=minutes], got {group!r}")
        origin, arrow, place = route.rpartition(">")
        for pair in filter(None, (part.strip() for part in modes.split(","))):
            mode, equals, minutes = pair.partition("=")
            if not equals or not minutes.strip().isdigit():
                raise ValueError(f"expected mode=minutes (whole minutes), got {pair!r}")
            entry = {"place": place, "mode": mode, "minutes": int(minutes)}
            if arrow:
                entry["origin"] = origin
            entries.append(entry)
    return entries


def _check_hh_mm(value: str | None) -> str | None:
    if value is not None and not _HH_MM.match(value):
        raise ValueError(f"expected HH:MM, got {value!r}")
    return value


class PlanningSettingsRead(BaseModel):
    wake_time: str | None = None
    sleep_time: str | None = None
    work_target_minutes: int
    preferred_work_windows: list[str] = []
    workdays: list[str] = list(DEFAULT_WORKDAYS)
    work_tag: str
    office_tag: str
    office_days_per_week: int | None = None
    office_min_minutes: int | None = None
    conventions: str | None = None
    travel_times: list[TravelTime] = []


class PlanningSettingsUpdate(BaseModel):
    """Partial update: a field left out is untouched, an explicit null resets it to its default (unset)."""

    wake_time: str | None = None
    sleep_time: str | None = None
    work_target_minutes: int | None = Field(default=None, ge=0, le=1440)
    preferred_work_windows: list[str] | None = None
    workdays: list[str] | None = None
    work_tag: str | None = None
    office_tag: str | None = None
    office_days_per_week: int | None = Field(default=None, ge=1, le=7)
    office_min_minutes: int | None = Field(default=None, ge=0, le=1440)
    conventions: str | None = Field(default=None, max_length=CONVENTIONS_MAX_LENGTH)
    travel_times: list[TravelTime] | None = Field(default=None, max_length=MAX_TRAVEL_TIMES)

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

    @field_validator("workdays")
    @classmethod
    def _workdays(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        days = [day.strip().lower() for day in value]
        unknown = [day for day in days if day not in WEEKDAYS]
        if unknown:
            raise ValueError(f"expected weekdays among {', '.join(WEEKDAYS)}, got {unknown!r}")
        return [day for day in WEEKDAYS if day in days]

    @field_validator("travel_times")
    @classmethod
    def _travel_times(cls, value: list[TravelTime] | None) -> list[TravelTime] | None:
        return _unique_travel_times(value)

    @field_validator("conventions")
    @classmethod
    def _conventions(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

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
    activity_suggestions: list[ActivitySuggestion] | None = None
    saved_plan: list[dict[str, Any]] | None = None
    warnings: list[str] = []
