import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.core.reminders.service import snooze_undated_escalation
from app.features.core.urgency_reset.schemas import UrgencyResetRead
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.organizer.tasks.schemas import TaskFilters, TaskRead, TaskUpdate
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_MAX_TASKS = 10_000


class UrgencyResetService:
    """Gives every task a fresh escalation clock.

    Escalation is derived (overdue deadline, or age for undated one-off tasks), so
    clearing the URGENT flag alone doesn't stick -- the next hourly reminder run
    re-escalates. Each kind of task needs its trigger pushed out instead:
    - one-off with an overdue deadline: deadline moves to today + `days`
    - one-off without a deadline: escalation is snoozed for `days`
    - recurring: only the flag is cleared (each cycle already starts fresh)
    Priority is never touched. All writes go through TaskService so the Notion
    write-through cache stays in sync.
    """

    def __init__(self, session: AsyncSession, task_service: TaskService) -> None:
        self._task_service = task_service
        self._working_memory_service = WorkingMemoryService(session)

    async def reset(self, days: int | None = None) -> UrgencyResetRead:
        settings = get_settings()
        days = days if days is not None else settings.urgency_reset_days
        now_local = local_now()
        now = now_local.replace(tzinfo=None)
        escalation_age = timedelta(days=settings.undated_task_escalation_days)

        urgency_reset = deadline_moved = snoozed = 0
        tasks = await self._task_service.get_tasks(TaskFilters(status="ACTIVE", limit=_MAX_TASKS))
        for task in tasks:
            was_urgent = task.urgency == "URGENT"
            if task.recurrence_rule is not None:
                if was_urgent:
                    await self._task_service.update_task(task.id, TaskUpdate(urgency="NORMAL"))
                    urgency_reset += 1
            elif task.deadline is not None:
                if task.deadline < now:
                    new_deadline = datetime.combine((now + timedelta(days=days)).date(), task.deadline.time())
                    await self._task_service.update_task(
                        task.id, TaskUpdate(deadline=new_deadline, urgency="NORMAL")
                    )
                    deadline_moved += 1
                    urgency_reset += was_urgent
                elif was_urgent:
                    await self._task_service.update_task(task.id, TaskUpdate(urgency="NORMAL"))
                    urgency_reset += 1
            elif was_urgent or _is_age_escalation_candidate(task, now_local, escalation_age):
                await snooze_undated_escalation(
                    self._working_memory_service, task.id, days,
                    task_service=self._task_service, current_urgency=task.urgency,
                )
                snoozed += 1
                urgency_reset += was_urgent

        logger.info(
            "Urgency reset: days=%d urgency_reset=%d deadline_moved=%d snoozed=%d",
            days, urgency_reset, deadline_moved, snoozed,
        )
        return UrgencyResetRead(
            days=days,
            tasks_urgency_reset=urgency_reset,
            tasks_deadline_moved=deadline_moved,
            tasks_snoozed=snoozed,
        )


def _is_age_escalation_candidate(task: TaskRead, now: datetime, escalation_age: timedelta) -> bool:
    return task.priority != "HIGH" and now - task.created_at >= escalation_age
