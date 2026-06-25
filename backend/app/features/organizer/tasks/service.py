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
from app.features.organizer.tasks.recurrence import compute_streak, missed_count
from app.features.organizer.tasks.repository import TaskRepository

logger = logging.getLogger(__name__)


def _compute_streak(dates: list[date], rule: str, today: date) -> int:
    return compute_streak(dates, rule, today)


def _missed_count(rule: str, completions: list[date], today: date) -> int:
    return missed_count(rule, completions, today)


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
