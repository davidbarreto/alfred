import logging
import math
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.overload.repository import OverloadLogRepository
from app.features.core.overload.schemas import (
    OverloadDayRead,
    OverloadLevel,
    OverloadSnapshot,
    OverloadStatusRead,
)
from app.features.core.overload.tables import OverloadLog
from app.features.core.reminders.schemas import ReminderSettingsRead
from app.features.core.reminders.settings_service import ReminderSettingsService
from app.features.organizer.tasks.recurrence import is_due_today
from app.features.organizer.tasks.schemas import TaskFilters
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_MAX_TASKS = 10_000
_STREAK_LOOKBACK_DAYS = 90
_LEVEL_RANK: dict[str, int] = {"ok": 0, "elevated": 1, "overloaded": 2}


def classify_level(overdue: int, urgent: int, settings: ReminderSettingsRead) -> OverloadLevel:
    """Overloaded at the configured thresholds; elevated from half of them."""
    if overdue >= settings.overload_overdue_threshold or urgent >= settings.overload_urgent_threshold:
        return "overloaded"
    if (
        overdue >= math.ceil(settings.overload_overdue_threshold / 2)
        or urgent >= math.ceil(settings.overload_urgent_threshold / 2)
    ):
        return "elevated"
    return "ok"


class OverloadService:
    """Measures how backed-up the task list is and keeps a daily record for statistics."""

    def __init__(self, session: AsyncSession, task_service: TaskService) -> None:
        self._task_service = task_service
        self._settings = ReminderSettingsService(session)
        self._repo = OverloadLogRepository(session)

    async def snapshot(self) -> OverloadSnapshot:
        settings = await self._settings.get()
        now = local_now().replace(tzinfo=None)
        tasks = await self._task_service.get_tasks(TaskFilters(status="ACTIVE", limit=_MAX_TASKS))

        overdue = urgent = active = 0
        for task in tasks:
            if task.recurrence_rule is not None and (
                not is_due_today(task.recurrence_rule, now.date()) or task.is_done_in_cycle
            ):
                continue
            active += 1
            if task.deadline is not None and task.deadline < now:
                overdue += 1
            if task.urgency == "URGENT":
                urgent += 1

        return OverloadSnapshot(
            level=classify_level(overdue, urgent, settings),
            overdue=overdue,
            urgent=urgent,
            active=active,
            overdue_threshold=settings.overload_overdue_threshold,
            urgent_threshold=settings.overload_urgent_threshold,
        )

    async def status(self) -> OverloadStatusRead:
        snapshot = await self.snapshot()
        streak = await self._streak_days(snapshot) if snapshot.level == "overloaded" else 0
        return OverloadStatusRead(**snapshot.model_dump(), streak_days=streak)

    async def history(self, days: int) -> list[OverloadDayRead]:
        since = local_now().date() - timedelta(days=days - 1)
        rows = await self._repo.get_days(since)
        return [OverloadDayRead.model_validate(row) for row in reversed(rows)]

    async def previous_level(self) -> OverloadLevel | None:
        """Level at the most recent recorded reminder run, before the current one."""
        latest = await self._repo.get_latest()
        return latest.last_level if latest is not None else None

    async def record_run(self, snapshot: OverloadSnapshot, listed: int, omitted: int) -> None:
        today = local_now().date()
        now = datetime.now(timezone.utc)
        row = await self._repo.get_day(today)
        if row is None:
            row = OverloadLog(
                date=today, level=snapshot.level, last_level=snapshot.level, peak_overdue=0,
                peak_urgent=0, peak_active=0, reminder_runs=0, tasks_listed=0, tasks_omitted=0,
            )
        if _LEVEL_RANK[snapshot.level] > _LEVEL_RANK[row.level]:
            row.level = snapshot.level
        row.last_level = snapshot.level
        row.peak_overdue = max(row.peak_overdue, snapshot.overdue)
        row.peak_urgent = max(row.peak_urgent, snapshot.urgent)
        row.peak_active = max(row.peak_active, snapshot.active)
        row.reminder_runs += 1
        row.tasks_listed += listed
        row.tasks_omitted += omitted
        if snapshot.level == "overloaded" and row.first_overloaded_at is None:
            row.first_overloaded_at = now
        await self._repo.save(row)
        logger.info(
            "Overload recorded: date=%s level=%s overdue=%d urgent=%d listed=%d omitted=%d",
            today, snapshot.level, snapshot.overdue, snapshot.urgent, listed, omitted,
        )

    async def _streak_days(self, snapshot: OverloadSnapshot) -> int:
        """Consecutive overloaded days up to today (today counts: the snapshot is live)."""
        today = local_now().date()
        rows = await self._repo.get_days(today - timedelta(days=_STREAK_LOOKBACK_DAYS))
        overloaded_days = {row.date for row in rows if row.level == "overloaded"}
        streak = 1
        day: date = today - timedelta(days=1)
        while day in overloaded_days:
            streak += 1
            day -= timedelta(days=1)
        return streak
