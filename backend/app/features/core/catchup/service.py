import logging

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.reminders.schemas import ReminderSettingsRead
from app.features.core.reminders.settings_service import ReminderSettingsService
from app.features.core.catchup import planner
from app.features.core.catchup.schemas import (
    CatchupApply,
    CatchupApplyRead,
    CatchupMove,
    CatchupRead,
    CatchupSuggestion,
    CatchupTask,
)
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_MAX_TASKS = 10_000


class CatchupService:
    """Suggests how to dig out of a task backlog and applies the suggestion the user accepts.

    Suggestions are recomputed on every call (never stored), and `apply` re-validates against
    fresh data, so a stale portal view can't move or drop a task that no longer qualifies.
    All writes go through TaskService so the Notion write-through cache stays in sync.
    """

    def __init__(self, session: AsyncSession, task_service: TaskService) -> None:
        self._task_service = task_service
        self._settings = ReminderSettingsService(session)

    async def get_suggestions(self) -> CatchupRead:
        settings = await self._settings.get()
        now, now_aware, tasks = await self._load()
        top = planner.top_tasks(tasks, now)
        suggestions = [
            s for s in (
                self._spread_suggestion(tasks, now, settings, exclude_ids=self._reserved_ids(tasks, now, now_aware, settings)),
                self._drop_suggestion(tasks, now, now_aware, settings),
                self._habits_suggestion(tasks, settings),
            ) if s is not None
        ]
        logger.debug("Catchup computed: top=%d suggestions=%s", len(top), [s.kind for s in suggestions])
        return CatchupRead(today_top=[_to_task(t, now) for t in top], suggestions=suggestions)

    async def apply(self, request: CatchupApply) -> CatchupApplyRead:
        settings = await self._settings.get()
        now, now_aware, tasks = await self._load()
        reserved = self._reserved_ids(tasks, now, now_aware, settings)

        if request.kind == "spread":
            moves = planner.plan_spread(tasks, now, settings.catchup_tasks_per_day, reserved)
            if len(moves) < 2:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing to spread")
            for move in moves:
                await self._task_service.update_task(move.task.id, TaskUpdate(deadline=move.new_deadline))
            logger.info("Catchup applied: kind=spread moved=%d", len(moves))
            return CatchupApplyRead(kind="spread", applied=len(moves), skipped=0)

        eligible = {t.id for t in planner.stale_tasks(tasks, now, now_aware, settings.catchup_stale_days)}
        wanted = set(request.task_ids) if request.task_ids is not None else eligible
        if not wanted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Nothing to drop")
        to_drop = sorted(wanted & eligible)
        for task_id in to_drop:
            await self._task_service.update_task(task_id, TaskUpdate(status="CANCELLED"))
        logger.info("Catchup applied: kind=drop dropped=%d skipped=%d", len(to_drop), len(wanted) - len(to_drop))
        return CatchupApplyRead(kind="drop", applied=len(to_drop), skipped=len(wanted) - len(to_drop))

    async def _load(self):
        now_aware = local_now()
        now = now_aware.replace(tzinfo=None)
        tasks = await self._task_service.get_tasks(TaskFilters(status="ACTIVE", limit=_MAX_TASKS))
        return now, now_aware, tasks

    @staticmethod
    def _reserved_ids(tasks, now, now_aware, settings: ReminderSettingsRead) -> set[int]:
        """Tasks the spread must leave alone: today's top picks and anything proposed for dropping."""
        top = {t.id for t in planner.top_tasks(tasks, now)}
        stale = {t.id for t in planner.stale_tasks(tasks, now, now_aware, settings.catchup_stale_days)}
        return top | stale

    @staticmethod
    def _spread_suggestion(tasks, now, settings: ReminderSettingsRead, exclude_ids: set[int]) -> CatchupSuggestion | None:
        moves = planner.plan_spread(tasks, now, settings.catchup_tasks_per_day, exclude_ids)
        if len(moves) < 2:
            return None
        last = max(m.new_deadline for m in moves).date()
        return CatchupSuggestion(
            kind="spread",
            title=f"Spread {len(moves)} overdue tasks over the next days",
            detail=(
                f"At most {settings.catchup_tasks_per_day} due per day, most important first, "
                f"through {last:%a %d %b}. Deadlines keep their time of day."
            ),
            moves=[
                CatchupMove(
                    task_id=m.task.id, title=m.task.title, priority=m.task.priority,
                    old_deadline=m.task.deadline, new_deadline=m.new_deadline,
                )
                for m in moves
            ],
            command="/catchupapply spread",
        )

    @staticmethod
    def _drop_suggestion(tasks, now, now_aware, settings: ReminderSettingsRead) -> CatchupSuggestion | None:
        stale = planner.stale_tasks(tasks, now, now_aware, settings.catchup_stale_days)
        if not stale:
            return None
        ids = ",".join(str(t.id) for t in stale)
        return CatchupSuggestion(
            kind="drop",
            title=f"Drop {len(stale)} stale task(s)?",
            detail=(
                f"Not high priority and overdue (or urgent with no date) for {settings.catchup_stale_days}+ days. "
                "Dropping cancels them; you can still find them under cancelled tasks."
            ),
            tasks=[_to_task(t, now) for t in stale],
            command=f"/catchupapply drop {ids}",
        )

    @staticmethod
    def _habits_suggestion(tasks, settings: ReminderSettingsRead) -> CatchupSuggestion | None:
        habits = planner.missed_habits(tasks, settings.catchup_missed_habit_threshold)
        if not habits:
            return None
        return CatchupSuggestion(
            kind="habits",
            title=f"{len(habits)} habit(s) you keep missing",
            detail=(
                f"Missed {settings.catchup_missed_habit_threshold}+ times this week. "
                "Consider lowering the frequency or dropping them."
            ),
            tasks=[
                CatchupTask(id=t.id, title=t.title, priority=t.priority, urgency=t.urgency, deadline=t.deadline)
                for t in habits
            ],
            applicable=False,
        )


def _to_task(task, now) -> CatchupTask:
    return CatchupTask(
        id=task.id, title=task.title, priority=task.priority, urgency=task.urgency,
        deadline=task.deadline, days_overdue=planner.days_overdue(task, now),
    )
