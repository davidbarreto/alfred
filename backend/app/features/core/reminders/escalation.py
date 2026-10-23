"""Pure rules for when a task escalates to URGENT and how often it is re-reminded."""
from datetime import timedelta

from app.features.core.reminders.schemas import ReminderSettingsRead

# Dedup TTLs set the reminder frequency against the hourly n8n cron (08:00-22:00).
# Each TTL sits 10 minutes short of the target interval: a marker written seconds
# after the hour must expire before the run that should re-remind, never after it.
_MARGIN = timedelta(minutes=10)
URGENT_DEDUP_TTL = {
    "HIGH": timedelta(minutes=50),  # every hourly run
    "MEDIUM": timedelta(hours=1, minutes=50),  # every 2 hours
    "LOW": timedelta(hours=3, minutes=50),  # every 4 hours
}
NORMAL_DEDUP_TTL = {
    "HIGH": timedelta(hours=3, minutes=50),  # ~4x/day (08, 12, 16, 20)
    "MEDIUM": timedelta(hours=7, minutes=50),  # ~2x/day (08, 16)
    "LOW": timedelta(hours=24),  # once a day
}
DAILY_DEDUP_TTL = timedelta(hours=24)  # once a day (marker keys are date-scoped)


def overdue_grace(priority: str, settings: ReminderSettingsRead) -> timedelta:
    """How long a task may stay overdue before it escalates to URGENT."""
    hours = {
        "HIGH": settings.overdue_grace_hours_high,
        "MEDIUM": settings.overdue_grace_hours_medium,
    }.get(priority, settings.overdue_grace_hours_low)
    return timedelta(hours=hours)


def undated_escalation_age(priority: str, settings: ReminderSettingsRead) -> timedelta:
    """How old an undated task may get before it escalates to URGENT."""
    days = {
        "HIGH": settings.undated_escalation_days_high,
        "MEDIUM": settings.undated_escalation_days_medium,
    }.get(priority, settings.undated_escalation_days_low)
    return timedelta(days=days)


def task_dedup_ttl(urgency: str, priority: str, overloaded: bool, settings: ReminderSettingsRead) -> timedelta:
    if urgency == "URGENT":
        ttl = URGENT_DEDUP_TTL.get(priority, URGENT_DEDUP_TTL["LOW"])
        if overloaded:
            ttl = max(ttl, timedelta(hours=settings.overload_urgent_interval_hours) - _MARGIN)
        return ttl
    return NORMAL_DEDUP_TTL.get(priority, NORMAL_DEDUP_TTL["LOW"])
