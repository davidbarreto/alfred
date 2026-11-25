import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.features.core.settings.metadata import setting
from app.features.organizer.activities.schemas import ActivitySuggestion
from app.features.organizer.travel_times.schemas import MAX_TRAVEL_TIMES
from app.shared.utils.time_text import WEEKDAYS

_HH_MM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_WINDOW = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")


DEFAULT_WORKDAYS = WEEKDAYS[:5]
CONVENTIONS_MAX_LENGTH = 2000
# One-way minutes assumed for in-person travel with no travel time saved (0 switches the assumption off), and how
# many more minutes walking may take than public transport and still be chosen.
DEFAULT_TRAVEL_MINUTES = 30
DEFAULT_WALK_TOLERANCE_MINUTES = 10
# What the day plan lists and assumes; each is a planning.* setting with this default.
DEFAULT_BACKLOG_STALE_DAYS = 60
DEFAULT_DUE_LOOKAHEAD_DAYS = 3
DEFAULT_ASSUMED_ESTIMATE_MINUTES = 30
DEFAULT_SHOPPING_RUN_MINUTES = 45
DEFAULT_STUDY_ITEMS_PER_PLAN = 5


HOME = "home"


class TravelTime(BaseModel):
    """Minutes door to door between two places by one mode, e.g. home to office by metro: 50.

    Two-way: the same minutes apply the other way round unless the reverse trip is listed too.
    `origin` defaults to home; `place` is the destination. Stored as rows between places
    (`organizer.travel_times`): "home" is the Home place, other names are everyday place names in lowercase.
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
    default_travel_minutes: int = DEFAULT_TRAVEL_MINUTES
    walk_tolerance_minutes: int = DEFAULT_WALK_TOLERANCE_MINUTES
    backlog_stale_days: int = DEFAULT_BACKLOG_STALE_DAYS
    due_lookahead_days: int = DEFAULT_DUE_LOOKAHEAD_DAYS
    assumed_estimate_minutes: int = DEFAULT_ASSUMED_ESTIMATE_MINUTES
    shopping_run_minutes: int = DEFAULT_SHOPPING_RUN_MINUTES
    study_items_per_plan: int = DEFAULT_STUDY_ITEMS_PER_PLAN


class PlanningSettingsUpdate(BaseModel):
    """Partial update: a field left out is untouched, an explicit null resets it to its default (unset)."""

    wake_time: str | None = setting("Wake time", "When the planned day starts. Empty = not set.", widget="time", group="Day")
    sleep_time: str | None = setting("Sleep time", "When the planned day ends. Empty = not set.", widget="time", group="Day")
    work_target_minutes: int | None = setting(
        "Work target per day", "Minutes of work to plan on a workday.", unit="min", group="Work", ge=0, le=1440,
    )
    preferred_work_windows: list[str] | None = setting(
        "Preferred work windows", "When work is placed first, as HH:MM-HH:MM.", widget="windows", group="Work",
    )
    workdays: list[str] | None = setting("Workdays", "", widget="weekdays", group="Work")
    work_tag: str | None = setting("Work tag", "Tasks and events with this tag count as work time.", group="Work")
    office_tag: str | None = setting("Office tag", "Events with this tag mark an office day.", group="Office")
    office_days_per_week: int | None = setting(
        "Office days per week", "Empty = no office target.", unit="days", group="Office", ge=1, le=7,
    )
    office_min_minutes: int | None = setting(
        "Minimum for an office day", "Empty = any length counts.", unit="min", group="Office", ge=0, le=1440,
    )
    conventions: str | None = setting(
        "Conventions", "Standing rules every plan should follow, in free text. Sent with every day plan.",
        widget="longtext", group="Rules", max_length=CONVENTIONS_MAX_LENGTH,
    )
    # Not on the settings page: travel times are rows between locations, edited on each location's page.
    travel_times: list[TravelTime] | None = Field(default=None, max_length=MAX_TRAVEL_TIMES)
    default_travel_minutes: int | None = setting(
        "Assumed travel when nothing is saved", "Minutes one way for a leg with no saved route. 0 = off.",
        unit="min", group="Travel", ge=0, le=600,
    )
    walk_tolerance_minutes: int | None = setting(
        "Walk instead of public transport", "When walking takes at most this many minutes longer.",
        unit="min", group="Travel", ge=0, le=120,
    )
    backlog_stale_days: int | None = setting(
        "Backlog task is old after", "The plan warns about undated tasks created longer ago than this.",
        unit="days", group="What the plan lists", ge=1, le=3650,
    )
    due_lookahead_days: int | None = setting(
        "Due tasks ahead", "Tasks due this many days after the planned range are listed as due too.",
        unit="days", group="What the plan lists", ge=0, le=60,
    )
    study_items_per_plan: int | None = setting(
        "Open items per study plan", "How many open items of each active study plan are listed.",
        unit="items", group="What the plan lists", ge=1, le=50,
    )
    assumed_estimate_minutes: int | None = setting(
        "Assumed task length", "What a task without an estimate is assumed to take (said in the warnings).",
        unit="min", group="What the plan lists", ge=5, le=480,
    )
    shopping_run_minutes: int | None = setting(
        "Shopping run", "How long the suggested shopping run takes.",
        unit="min", group="What the plan lists", ge=5, le=480,
    )

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
    # Events: the linked place's name (else the calendar's location text); routine steps: the step's location.
    location: str | None = None
    place_id: int | None = None
    # Travel of an event with no location and no travel minutes: the default was assumed (ask the user).
    assumed: bool | None = None
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
    by_category: dict[str, int] = {}


class TripDay(BaseModel):
    """One day of a trip that overlaps the plan: the user is away (or leaving/coming back) that day."""

    trip_id: int
    name: str
    day: int
    days: int
    # Legs, check-ins/outs and visits of that day as ready-to-read lines, times in the zone of where they happen.
    agenda: list[str] = []
    # Only on the day the user leaves home for the trip's first flight.
    leave_home_at: str | None = None


class DayRead(BaseModel):
    date: str
    timeline: list[TimelineItem] = []
    routine_blocks: list[RoutineBlock] = []
    all_day: list[AllDayItem] = []
    work: WorkSummary
    # Public holidays of the planning calendar (first HOLIDAY_CALENDARS entry) as "Name (PT)"; omitted when none.
    holidays: list[str] | None = None
    trips: list[TripDay] | None = None


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
    holidays: list[str] | None = None
    trips: list[TripDay] | None = None
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
