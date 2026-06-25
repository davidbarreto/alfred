import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.features.organizer.tasks.tables import Task
from app.features.organizer.tasks.schemas import (
    TaskCompletionRead,
    TaskCreate,
    TaskRead,
    TaskUpdate,
    TaskFilters,
)
from app.features.organizer.tasks.repository import TaskRepository

logger = logging.getLogger(__name__)


def _compute_streak(dates: list[date], rule: str, today: date) -> int:
    if not dates:
        return 0
    sorted_dates = sorted(set(dates), reverse=True)

    if "FREQ=DAILY" in rule:
        if sorted_dates[0] < today - timedelta(days=1):
            return 0
        streak = 0
        expected = sorted_dates[0]
        for d in sorted_dates:
            if d == expected:
                streak += 1
                expected -= timedelta(days=1)
            else:
                break
        return streak

    elif "FREQ=WEEKLY" in rule:
        def _iso_week(d: date) -> tuple[int, int]:
            iso = d.isocalendar()
            return (iso[0], iso[1])

        weeks = sorted(set(_iso_week(d) for d in sorted_dates), reverse=True)
        if not weeks:
            return 0
        last_week = _iso_week(today - timedelta(weeks=1))
        if weeks[0] < last_week:
            return 0
        streak = 0
        yr, wk = weeks[0]
        for w_yr, w_wk in weeks:
            if (w_yr, w_wk) == (yr, wk):
                streak += 1
                prev = date.fromisocalendar(yr, wk, 1) - timedelta(weeks=1)
                yr, wk = _iso_week(prev)
            else:
                break
        return streak

    elif "FREQ=MONTHLY" in rule:
        def _month_key(d: date) -> tuple[int, int]:
            return (d.year, d.month)

        months = sorted(set(_month_key(d) for d in sorted_dates), reverse=True)
        if not months:
            return 0
        first_of_month = today.replace(day=1)
        last_month = _month_key(first_of_month - timedelta(days=1))
        if months[0] < last_month:
            return 0
        streak = 0
        yr, mo = months[0]
        for m_yr, m_mo in months:
            if (m_yr, m_mo) == (yr, mo):
                streak += 1
                prev = date(yr, mo, 1) - timedelta(days=1)
                yr, mo = prev.year, prev.month
            else:
                break
        return streak

    else:
        return len(sorted_dates)


_BYDAY_MAP = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _parse_byday(rule: str) -> list[int] | None:
    for part in rule.split(";"):
        if part.startswith("BYDAY="):
            days = [d.strip().upper() for d in part[len("BYDAY="):].split(",")]
            result = [_BYDAY_MAP[d] for d in days if d in _BYDAY_MAP]
            return result if result else None
    return None


def _missed_count(rule: str, completions: list[date], today: date) -> int:
    completion_set = set(completions)

    if "FREQ=DAILY" in rule:
        # Unchecked checkbox already communicates "not done today"
        return 0

    elif "FREQ=WEEKLY" in rule:
        week_start = today - timedelta(days=today.weekday())  # Monday of this week
        byday = _parse_byday(rule)
        if byday:
            return sum(
                1
                for day_num in byday
                if (scheduled := week_start + timedelta(days=day_num)) < today
                and scheduled not in completion_set
            )
        else:
            # No BYDAY: late from Friday (weekday 4) if nothing done this week
            if today.weekday() >= 4:
                return 0 if any(week_start <= d < today for d in completion_set) else 1
            return 0

    elif "FREQ=MONTHLY" in rule:
        if today.day >= 25:
            month_start = today.replace(day=1)
            return 0 if any(month_start <= d < today for d in completion_set) else 1
        return 0

    return 0


class TaskService:

    def __init__(self, provider: StorageProvider, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session
        self._repo = TaskRepository(session)

    async def get_task(self, task_id: int) -> TaskRead | None:
        task_orm = await self._repo.get_task(task_id)
        if task_orm is None:
            return None
        task_read = TaskRead.model_validate(task_orm)
        if task_orm.recurrence_rule is not None:
            today = date.today()
            completed = await self._repo.get_completed_task_ids_for_date([task_id], today)
            task_read.is_done_today = task_id in completed
            completions_map = await self._repo.get_completions_by_task([task_id])
            dates = completions_map.get(task_id, [])
            task_read.total_completions = len(dates)
            task_read.streak = _compute_streak(dates, task_orm.recurrence_rule, today)
            task_read.missed_count = _missed_count(task_orm.recurrence_rule, dates, today)
        return task_read

    async def get_tasks(self, filters: TaskFilters) -> list[TaskRead]:
        tasks_orm = await self._repo.get_tasks(filters)
        task_reads = [TaskRead.model_validate(t) for t in tasks_orm]
        recurring_ids = [t.id for t in task_reads if t.recurrence_rule is not None]
        if recurring_ids:
            today = date.today()
            completed_today = await self._repo.get_completed_task_ids_for_date(recurring_ids, today)
            completions_map = await self._repo.get_completions_by_task(recurring_ids)
            recurring_orm = {t.id: t for t in tasks_orm if t.recurrence_rule is not None}
            for task in task_reads:
                if task.recurrence_rule is None:
                    continue
                task.is_done_today = task.id in completed_today
                dates = completions_map.get(task.id, [])
                task.total_completions = len(dates)
                task.streak = _compute_streak(dates, recurring_orm[task.id].recurrence_rule, today)
                task.missed_count = _missed_count(recurring_orm[task.id].recurrence_rule, dates, today)
        return task_reads

    async def create_task(self, task_create: TaskCreate) -> TaskRead:
        task_record = await self._provider.create(task_create.model_dump(), self._session)
        task_orm = await self._repo.create_task(task_create, task_record["id"])
        logger.info("Task created: id=%d title=%r", task_orm.id, task_create.title)
        return TaskRead.model_validate(task_orm)

    async def update_task(self, task_id: int, task_update: TaskUpdate) -> TaskRead | None:
        task = await self._repo.get_task(task_id)
        if task is None:
            logger.debug("Task update: id=%d not found", task_id)
            return None
        await self._provider.update(
            task.provider_id,
            task_update.model_dump(exclude_unset=True),
            self._session,
        )
        task_orm = await self._repo.update_task(task_id, task_update)
        logger.info("Task updated: id=%d fields=%s", task_id, list(task_update.model_dump(exclude_unset=True).keys()))
        return TaskRead.model_validate(task_orm)

    async def complete_task(
        self, task_id: int, occurrence_date: date | None = None
    ) -> TaskRead | TaskCompletionRead | None:
        task = await self._repo.get_task(task_id)
        if task is None:
            return None

        if task.recurrence_rule is None:
            task_orm = await self._repo.update_task(task_id, TaskUpdate(status="DONE"))
            logger.info("Task completed (non-recurring): id=%d", task_id)
            result = TaskRead.model_validate(task_orm)
            result.is_done_today = True
            return result

        occ_date = occurrence_date or date.today()
        existing = await self._repo.get_completion(task_id, occ_date)
        if existing is not None:
            return TaskCompletionRead.model_validate(existing)

        completion = await self._repo.complete_occurrence(task_id, occ_date)
        logger.info("Task occurrence completed: id=%d occurrence_date=%s", task_id, occ_date)
        return TaskCompletionRead.model_validate(completion)

    async def get_completions_history(self, days: int) -> list[TaskCompletionRead]:
        since = date.today() - timedelta(days=days)
        completions = await self._repo.get_all_completions_since(since)
        return [TaskCompletionRead.model_validate(c) for c in completions]

    async def get_task_completions(self, task_id: int) -> list[TaskCompletionRead] | None:
        task = await self._repo.get_task(task_id)
        if task is None:
            return None
        completions = await self._repo.get_task_completions(task_id)
        return [TaskCompletionRead.model_validate(c) for c in completions]

    async def cancel_task(self, task_id: int) -> TaskRead | None:
        task = await self._repo.get_task(task_id)
        if task is None:
            return None

        if task.recurrence_rule is None:
            raise ValueError("Task is not recurring. Use /done instead.")

        if task.status in ("DONE", "CANCELLED"):
            raise ValueError(f"Task is already in terminal state: {task.status.lower()}")

        task_orm = await self._repo.update_task(task_id, TaskUpdate(status="CANCELLED"))
        logger.info("Task cancelled: id=%d", task_id)
        return TaskRead.model_validate(task_orm)

    async def delete_task(self, task_id: int) -> None:
        task = await self._repo.get_task(task_id)
        if task:
            await self._provider.delete(task.provider_id, self._session)
            await self._repo.delete_task(task_id)
            logger.info("Task deleted: id=%d", task_id)
