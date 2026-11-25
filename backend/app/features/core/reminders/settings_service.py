import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.core.reminders.schemas import ReminderSettingsRead, ReminderSettingsUpdate
from app.features.core.settings.service import SettingService

logger = logging.getLogger(__name__)

_KEY_PREFIX = "reminders."

# Tunable from the portal. Stored in core.settings as "reminders.<field>"; a missing
# row falls back to the default below, or to its env var for the fields in `defaults()`.
DEFAULTS: dict[str, int] = {
    "overload_overdue_threshold": 5,
    "overload_urgent_threshold": 4,
    "overload_max_listed": 5,
    "overload_urgent_interval_hours": 4,
    "overdue_grace_hours_high": 0,
    "overdue_grace_hours_medium": 48,
    "overdue_grace_hours_low": 168,
    "undated_escalation_days_high": 7,
    "undated_escalation_days_medium": 21,
    "undated_escalation_days_low": 45,
    "catchup_tasks_per_day": 3,
    "catchup_stale_days": 30,
    "catchup_missed_habit_threshold": 3,
}


def defaults() -> dict[str, int]:
    """Every field's default: `DEFAULTS` plus the two that come from env (URGENCY_RESET_DAYS, UNDATED_TASK_SNOOZE_DAYS)."""
    env = get_settings()
    return {
        **DEFAULTS,
        "urgency_reset_days": env.urgency_reset_days,
        "undated_task_snooze_days": env.undated_task_snooze_days,
    }


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class ReminderSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> ReminderSettingsRead:
        values: dict[str, int] = {}
        for field, default in defaults().items():
            raw = await self._settings.get_value(_key(field))
            values[field] = int(raw) if raw else default
        return ReminderSettingsRead(**values)

    async def update(self, data: ReminderSettingsUpdate) -> ReminderSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Reminder settings updated: fields=%s", list(changes.keys()))
        return await self.get()
