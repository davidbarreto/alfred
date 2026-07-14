import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.core.reminders.schemas import ReminderDigest
from app.features.core.working_memory.repository import WorkingMemoryRepository
from app.features.core.working_memory.schemas import WorkingMemoryCreate, WorkingMemoryFilters
from app.features.core.working_memory.service import WorkingMemoryService
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.shopping.repository import ShoppingRepository
from app.features.organizer.shopping.schemas import ShoppingItemFilters
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_TASK_LOOKAHEAD = timedelta(hours=24)
_EVENT_LOOKAHEAD = timedelta(hours=2)
_URGENT_DEDUP_TTL = timedelta(hours=1)
_NORMAL_DEDUP_TTL = timedelta(hours=24)


def undated_escalation_snooze_key(task_id: int) -> str:
    return f"task_escalation_snooze:{task_id}"


async def snooze_undated_escalation(
    working_memory_service: WorkingMemoryService, task_id: int, days: int | None = None
) -> datetime:
    """Shared by the Telegram `task.snooze` command and the portal's snooze button."""
    days = days if days is not None else get_settings().undated_task_snooze_days
    key = undated_escalation_snooze_key(task_id)
    for marker in await working_memory_service.list(WorkingMemoryFilters(key=key, active_only=True, limit=1)):
        await working_memory_service.delete(marker.id)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    await working_memory_service.create(WorkingMemoryCreate(key=key, value="snoozed", expires_at=expires_at))
    logger.info("Task escalation snoozed: id=%d days=%d until=%s", task_id, days, expires_at.isoformat())
    return expires_at


class ReminderService:
    def __init__(self, session: AsyncSession, task_service: TaskService) -> None:
        self._session = session
        self._task_service = task_service
        self._event_repo = CalendarEventRepository(session)
        self._shopping_repo = ShoppingRepository(session)
        self._working_memory_repo = WorkingMemoryRepository(session)

    async def build_due_digest(self) -> ReminderDigest:
        now = local_now().replace(tzinfo=None)
        today = now.date()

        lines: list[str] = []
        lines.extend(await self._collect_task_lines(now, today))
        lines.extend(await self._collect_event_lines(now, today))
        lines.extend(await self._collect_shopping_lines(today))

        text = "\n".join(["⏰ Reminders", *lines]) if lines else ""
        return ReminderDigest(date=today, has_content=bool(lines), text=text)

    async def _collect_task_lines(self, now: datetime, today) -> list[str]:
        lines: list[str] = []
        lines.extend(await self._collect_dated_task_lines(now, today))
        lines.extend(await self._collect_undated_task_lines(today))
        return lines

    async def _collect_dated_task_lines(self, now: datetime, today) -> list[str]:
        tasks = await self._task_service.get_tasks(
            TaskFilters(status="ACTIVE", deadline_to=now + _TASK_LOOKAHEAD, limit=100)
        )
        lines: list[str] = []
        for task in tasks:
            if task.deadline is None:
                continue
            is_overdue = task.deadline < now
            if not is_overdue and task.deadline > now + _TASK_LOOKAHEAD:
                continue

            urgency = task.urgency
            if urgency == "NORMAL":
                await self._task_service.update_task(task.id, TaskUpdate(urgency="URGENT"))
                logger.info(
                    "Task urgency escalated: id=%d title=%r deadline=%s",
                    task.id, task.title, task.deadline,
                )
                urgency = "URGENT"

            if await self._already_reminded("task", task.id, today):
                continue

            label = "Overdue" if is_overdue else "Due today"
            lines.append(f"{label} ({urgency}): {task.title}")
            ttl = _URGENT_DEDUP_TTL if urgency == "URGENT" or task.priority == "HIGH" else _NORMAL_DEDUP_TTL
            await self._mark_reminded("task", task.id, today, ttl)
        return lines

    async def _collect_undated_task_lines(self, today) -> list[str]:
        tasks = await self._task_service.get_tasks(TaskFilters(status="ACTIVE", limit=100))
        undated = [task for task in tasks if task.deadline is None]

        now = local_now()
        escalation_age = timedelta(days=get_settings().undated_task_escalation_days)
        escalated = []
        quiet = []
        for task in undated:
            if await self._is_escalation_snoozed(task.id):
                quiet.append(task)
                continue

            if (
                task.urgency == "NORMAL"
                and task.priority != "HIGH"
                and now - task.created_at >= escalation_age
            ):
                task = await self._task_service.update_task(task.id, TaskUpdate(urgency="URGENT"))
                logger.info(
                    "Task urgency escalated: id=%d title=%r reason=no_deadline_stale created_at=%s",
                    task.id, task.title, task.created_at,
                )
            if task.urgency == "URGENT" or task.priority == "HIGH":
                escalated.append(task)
            else:
                quiet.append(task)

        lines: list[str] = []
        for task in escalated:
            if await self._already_reminded("task", task.id, today):
                continue
            lines.append(f"No due date ({task.urgency}): {task.title}")
            ttl = _URGENT_DEDUP_TTL if task.urgency == "URGENT" or task.priority == "HIGH" else _NORMAL_DEDUP_TTL
            await self._mark_reminded("task", task.id, today, ttl)

        if quiet and not await self._already_reminded("task_undated_summary", 0, today):
            lines.append(f"{len(quiet)} other task(s) without a due date")
            await self._mark_reminded("task_undated_summary", 0, today, _NORMAL_DEDUP_TTL)

        return lines

    async def _collect_event_lines(self, now: datetime, today) -> list[str]:
        events = await self._event_repo.get_events(
            EventFilters(start_from=now, start_to=now + _EVENT_LOOKAHEAD, limit=50)
        )
        lines: list[str] = []
        for event in events:
            if await self._already_reminded("event", event.id, today):
                continue
            lines.append(f"Starting soon ({event.start_datetime.strftime('%H:%M')}): {event.title}")
            await self._mark_reminded("event", event.id, today, _NORMAL_DEDUP_TTL)
        return lines

    async def _collect_shopping_lines(self, today) -> list[str]:
        items = await self._shopping_repo.list(ShoppingItemFilters(status="pending", limit=100))
        if not items:
            return []
        if await self._already_reminded("shopping", 0, today):
            return []
        await self._mark_reminded("shopping", 0, today, _NORMAL_DEDUP_TTL)
        return [f"Shopping list still has {len(items)} pending item(s)"]

    async def _is_escalation_snoozed(self, task_id: int) -> bool:
        existing = await self._working_memory_repo.list(
            WorkingMemoryFilters(key=undated_escalation_snooze_key(task_id), active_only=True, limit=1)
        )
        return bool(existing)

    async def _already_reminded(self, kind: str, entity_id: int, today) -> bool:
        key = f"reminder:{kind}:{entity_id}:{today.isoformat()}"
        existing = await self._working_memory_repo.list(
            WorkingMemoryFilters(key=key, active_only=True, limit=1)
        )
        return bool(existing)

    async def _mark_reminded(self, kind: str, entity_id: int, today, ttl: timedelta) -> None:
        key = f"reminder:{kind}:{entity_id}:{today.isoformat()}"
        try:
            await self._working_memory_repo.create(
                WorkingMemoryCreate(key=key, value="reminded", expires_at=datetime.now(timezone.utc) + ttl)
            )
        except IntegrityError:
            # Concurrent build_due_digest calls can both pass _already_reminded before either
            # commits; the unique constraint on key rejects the loser here instead of duplicating.
            await self._session.rollback()
            logger.debug("Reminder dedup marker already exists: key=%s", key)
