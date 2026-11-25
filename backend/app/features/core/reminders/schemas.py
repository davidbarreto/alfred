from datetime import date

from pydantic import BaseModel

from app.features.core.settings.metadata import setting


class ReminderDigest(BaseModel):
    date: date
    has_content: bool
    text: str


class ReminderSettingsRead(BaseModel):
    overload_overdue_threshold: int
    overload_urgent_threshold: int
    overload_max_listed: int
    overload_urgent_interval_hours: int
    overdue_grace_hours_high: int
    overdue_grace_hours_medium: int
    overdue_grace_hours_low: int
    undated_escalation_days_high: int
    undated_escalation_days_medium: int
    undated_escalation_days_low: int
    catchup_tasks_per_day: int
    catchup_stale_days: int
    catchup_missed_habit_threshold: int
    urgency_reset_days: int
    undated_task_snooze_days: int


class ReminderSettingsUpdate(BaseModel):
    """Partial update: a field left out, or sent as null, is untouched."""

    overload_overdue_threshold: int | None = setting(
        "Overdue tasks", "Overloaded at this many overdue tasks…",
        unit="tasks", group="When am I overloaded?", ge=1, le=100,
    )
    overload_urgent_threshold: int | None = setting(
        "Urgent tasks", "…or this many urgent tasks. Elevated from half.",
        unit="tasks", group="When am I overloaded?", ge=1, le=100,
    )
    overload_max_listed: int | None = setting(
        "Tasks per message", "Extra tasks rotate into later messages.",
        unit="tasks", group="Reminders while overloaded", ge=1, le=50,
    )
    overload_urgent_interval_hours: int | None = setting(
        "Urgent re-remind every", "Never faster than the normal cadence.",
        unit="hours", group="Reminders while overloaded", ge=1, le=24,
    )
    overdue_grace_hours_high: int | None = setting(
        "High priority", "Hours overdue before a high-priority task becomes urgent.",
        unit="hours overdue", group="Escalate overdue tasks to Urgent after", ge=0, le=24 * 90,
    )
    overdue_grace_hours_medium: int | None = setting(
        "Medium priority", "Hours overdue before a medium-priority task becomes urgent.",
        unit="hours overdue", group="Escalate overdue tasks to Urgent after", ge=0, le=24 * 90,
    )
    overdue_grace_hours_low: int | None = setting(
        "Low priority", "Hours overdue before a low-priority task becomes urgent.",
        unit="hours overdue", group="Escalate overdue tasks to Urgent after", ge=0, le=24 * 90,
    )
    undated_escalation_days_high: int | None = setting(
        "High priority", "Age of an undated high-priority task before it becomes urgent. 0 = never escalate by age.",
        unit="days old", group="Escalate undated tasks to Urgent after", ge=0, le=365,
    )
    undated_escalation_days_medium: int | None = setting(
        "Medium priority", "0 = never escalate by age.",
        unit="days old", group="Escalate undated tasks to Urgent after", ge=0, le=365,
    )
    undated_escalation_days_low: int | None = setting(
        "Low priority", "0 = never escalate by age.",
        unit="days old", group="Escalate undated tasks to Urgent after", ge=0, le=365,
    )
    catchup_tasks_per_day: int | None = setting(
        "Spread: tasks per day", "At most this many due on one day.",
        unit="tasks", group="Catch-up plan", ge=1, le=20,
    )
    catchup_stale_days: int | None = setting(
        "Stale after", "Non-high tasks overdue this long may be dropped.",
        unit="days overdue", group="Catch-up plan", ge=7, le=365,
    )
    catchup_missed_habit_threshold: int | None = setting(
        "Missed habit after", "A recurring task missed this many times this week is flagged.",
        unit="misses this week", group="Catch-up plan", ge=1, le=7,
    )
    urgency_reset_days: int | None = setting(
        "Push deadlines / snooze by", "What the urgency reset (and Resume after a pause) moves deadlines by.",
        unit="days", group="Urgency reset and snooze", ge=1, le=365,
    )
    undated_task_snooze_days: int | None = setting(
        "Snooze an undated task for", "How long a snoozed task stays out of age escalation, when no days are given.",
        unit="days", group="Urgency reset and snooze", ge=1, le=365,
    )
