from pydantic import BaseModel

from app.features.core.settings.metadata import setting

# The constants the briefing used before they became briefing.* settings.
DEFAULT_LOOKAHEAD_DAYS = 3
DEFAULT_HOLIDAY_LOOKAHEAD_DAYS = 7
DEFAULT_MAX_TASKS_TODAY = 8
DEFAULT_MAX_TASKS_UPCOMING = 4
DEFAULT_MAX_EVENTS_TODAY = 8
DEFAULT_MAX_EVENTS_UPCOMING = 4
DEFAULT_MAX_SHOPPING_ITEMS = 6
DEFAULT_MAX_RECURRING_ITEMS = 5


class BriefingSettingsRead(BaseModel):
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS
    holiday_lookahead_days: int = DEFAULT_HOLIDAY_LOOKAHEAD_DAYS
    max_tasks_today: int = DEFAULT_MAX_TASKS_TODAY
    max_tasks_upcoming: int = DEFAULT_MAX_TASKS_UPCOMING
    max_events_today: int = DEFAULT_MAX_EVENTS_TODAY
    max_events_upcoming: int = DEFAULT_MAX_EVENTS_UPCOMING
    max_shopping_items: int = DEFAULT_MAX_SHOPPING_ITEMS
    max_recurring_items: int = DEFAULT_MAX_RECURRING_ITEMS


class BriefingSettingsUpdate(BaseModel):
    """Partial update: a field left out, or null, is untouched."""

    lookahead_days: int | None = setting(
        "Tasks and events ahead", "Days the morning briefing covers, today included (also the dashboard's upcoming events).",
        unit="days", group="Looking ahead", ge=1, le=14,
    )
    holiday_lookahead_days: int | None = setting(
        "Holidays ahead", "Public holidays this many days ahead are listed.",
        unit="days", group="Looking ahead", ge=0, le=60,
    )
    max_tasks_today: int | None = setting(
        "Tasks due today", "Spelled out in the morning briefing; the rest are counted.",
        unit="tasks", group="Items listed in the morning briefing", ge=1, le=50,
    )
    max_tasks_upcoming: int | None = setting(
        "Upcoming tasks", "", unit="tasks", group="Items listed in the morning briefing", ge=0, le=50,
    )
    max_events_today: int | None = setting(
        "Events today", "", unit="events", group="Items listed in the morning briefing", ge=1, le=50,
    )
    max_events_upcoming: int | None = setting(
        "Upcoming events", "", unit="events", group="Items listed in the morning briefing", ge=0, le=50,
    )
    max_shopping_items: int | None = setting(
        "Shopping items", "", unit="items", group="Items listed in the morning briefing", ge=0, le=50,
    )
    max_recurring_items: int | None = setting(
        "Recurring purchases due", "", unit="items", group="Items listed in the morning briefing", ge=0, le=50,
    )
