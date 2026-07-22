import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

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
from app.features.organizer.tasks.recurrence import is_due_today
from app.features.organizer.tasks.schemas import TaskFilters, TaskUpdate
from app.features.organizer.tasks.service import TaskService
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_TASK_LOOKAHEAD = timedelta(hours=24)
_EVENT_LOOKAHEAD = timedelta(hours=2)
# Dedup TTLs set the reminder frequency against the hourly n8n cron (08:00-22:00).
# Each TTL sits 10 minutes short of the target interval: a marker written seconds
# after the hour must expire before the run that should re-remind, never after it.
_URGENT_DEDUP_TTL = timedelta(minutes=50)  # every hourly run
_HIGH_DEDUP_TTL = timedelta(hours=3, minutes=50)  # ~4x/day (08, 12, 16, 20)
_MEDIUM_DEDUP_TTL = timedelta(hours=7, minutes=50)  # ~2x/day (08, 16)
_DAILY_DEDUP_TTL = timedelta(hours=24)  # once a day (marker keys are date-scoped)


_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _task_dedup_ttl(urgency: str, priority: str) -> timedelta:
    if urgency == "URGENT":
        return _URGENT_DEDUP_TTL
    if priority == "HIGH":
        return _HIGH_DEDUP_TTL
    if priority == "MEDIUM":
        return _MEDIUM_DEDUP_TTL
    return _DAILY_DEDUP_TTL


@dataclass
class _TaskReminder:
    task: Any  # TaskRead; typed Any to avoid a schemas import cycle risk
    urgency: str
    is_overdue: bool = False


def _task_sort_key(entry: _TaskReminder) -> tuple:
    return (
        _PRIORITY_ORDER.get(entry.task.priority, len(_PRIORITY_ORDER)),
        0 if entry.is_overdue else 1,
        entry.task.deadline or datetime.max,
    )


def _format_task_line(entry: _TaskReminder, today: date) -> str:
    details = [entry.task.priority]
    deadline = entry.task.deadline
    if entry.is_overdue:
        details.append("overdue")
    elif deadline is not None:
        prefix = "due" if deadline.date() == today else "due tomorrow"
        details.append(f"{prefix} {deadline.strftime('%H:%M')}")
    return f"- {entry.task.title} ({', '.join(details)})"


def undated_escalation_snooze_key(task_id: int) -> str:
    return f"task_escalation_snooze:{task_id}"


async def snooze_undated_escalation(
    working_memory_service: WorkingMemoryService, task_id: int, days: int | None = None
) -> datetime:
    """Shared by the Telegram `task.snooze` command and the portal's snooze button."""
    days = days if days is not None else get_settings().undated_task_snooze_days
    key = undated_escalation_snooze_key(task_id)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    await working_memory_service.upsert(WorkingMemoryCreate(key=key, value="snoozed", expires_at=expires_at))
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
        entries = await self._collect_dated_task_entries(now, today)
        undated_entries, summary_lines = await self._collect_undated_task_entries(today)
        entries.extend(undated_entries)

        urgent = sorted((e for e in entries if e.urgency == "URGENT"), key=_task_sort_key)
        normal = sorted((e for e in entries if e.urgency != "URGENT"), key=_task_sort_key)

        lines: list[str] = []
        if urgent:
            lines.append("Urgent tasks:")
            lines.extend(_format_task_line(entry, today) for entry in urgent)
        if normal:
            if lines:
                lines.append("")
            lines.append("Normal tasks:")
            lines.extend(_format_task_line(entry, today) for entry in normal)
        lines.extend(summary_lines)
        return lines

    async def _collect_dated_task_entries(self, now: datetime, today) -> list[_TaskReminder]:
        tasks = await self._task_service.get_tasks(
            TaskFilters(status="ACTIVE", deadline_to=now + _TASK_LOOKAHEAD, limit=100)
        )
        entries: list[_TaskReminder] = []
        for task in tasks:
            if task.deadline is None:
                continue
            if task.recurrence_rule is not None and (
                not is_due_today(task.recurrence_rule, today) or task.is_done_in_cycle
            ):
                continue
            is_overdue = task.deadline < now
            if not is_overdue and task.deadline > now + _TASK_LOOKAHEAD:
                continue

            urgency = task.urgency
            if is_overdue and urgency == "NORMAL":
                await self._task_service.update_task(task.id, TaskUpdate(urgency="URGENT"))
                logger.info(
                    "Task urgency escalated: id=%d title=%r deadline=%s",
                    task.id, task.title, task.deadline,
                )
                urgency = "URGENT"

            if await self._already_reminded("task", task.id, today):
                continue

            entries.append(_TaskReminder(task=task, urgency=urgency, is_overdue=is_overdue))
            await self._mark_reminded("task", task.id, today, _task_dedup_ttl(urgency, task.priority))
        return entries

    async def _collect_undated_task_entries(self, today) -> tuple[list[_TaskReminder], list[str]]:
        tasks = await self._task_service.get_tasks(TaskFilters(status="ACTIVE", limit=100))
        undated = [task for task in tasks if task.deadline is None]

        now = local_now()
        escalation_age = timedelta(days=get_settings().undated_task_escalation_days)
        escalated = []
        quiet = []
        for task in undated:
            if task.recurrence_rule is not None and (
                not is_due_today(task.recurrence_rule, today) or task.is_done_in_cycle
            ):
                continue
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

        entries: list[_TaskReminder] = []
        for task in escalated:
            if await self._already_reminded("task", task.id, today):
                continue
            entries.append(_TaskReminder(task=task, urgency=task.urgency))
            await self._mark_reminded("task", task.id, today, _task_dedup_ttl(task.urgency, task.priority))

        summary_lines: list[str] = []
        if quiet and not await self._already_reminded("task_undated_summary", 0, today):
            summary_lines.append(f"{len(quiet)} other task(s) without a due date")
            await self._mark_reminded("task_undated_summary", 0, today, _DAILY_DEDUP_TTL)

        return entries, summary_lines

    async def _collect_event_lines(self, now: datetime, today) -> list[str]:
        events = await self._event_repo.get_events(
            EventFilters(start_from=now, start_to=now + _EVENT_LOOKAHEAD, limit=50)
        )
        lines: list[str] = []
        for event in events:
            if await self._already_reminded("event", event.id, today):
                continue
            lines.append(f"Starting soon ({event.start_datetime.strftime('%H:%M')}): {event.title}")
            await self._mark_reminded("event", event.id, today, _DAILY_DEDUP_TTL)
        return lines

    async def _collect_shopping_lines(self, today) -> list[str]:
        items = await self._shopping_repo.list(ShoppingItemFilters(status="pending", limit=100))
        if not items:
            return []
        if await self._already_reminded("shopping", 0, today):
            return []
        await self._mark_reminded("shopping", 0, today, _DAILY_DEDUP_TTL)
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
        # Upsert: the key is unique and expired rows linger, so re-reminding the same
        # entity later the same day must refresh expires_at instead of failing the insert.
        key = f"reminder:{kind}:{entity_id}:{today.isoformat()}"
        await self._working_memory_repo.upsert(
            WorkingMemoryCreate(key=key, value="reminded", expires_at=datetime.now(timezone.utc) + ttl)
        )
