from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.tasks.recurrence import is_due_today, missed_count
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters
from app.shared.timezone import local_now

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = frozenset({"TODO", "DOING"})


async def build_daily_context(session: AsyncSession) -> str:
    """Build a compact today-snapshot block for the chat system prompt."""
    try:
        return await _build(session)
    except Exception:
        logger.exception("Failed to build daily context — skipping")
        return ""


async def _build(session: AsyncSession) -> str:
    today = local_now().date()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    task_repo = TaskRepository(session)
    tasks_orm = await task_repo.get_tasks(
        TaskFilters(deadline_to=today_end, include_recurring=True, limit=200)
    )
    active_tasks = [t for t in tasks_orm if t.status in _ACTIVE_STATUSES]

    recurring_ids = [t.id for t in active_tasks if t.recurrence_rule]
    completed_today: set[int] = set()
    completions_map: dict[int, list[date]] = {}
    if recurring_ids:
        completed_today = await task_repo.get_completed_task_ids_for_date(recurring_ids, today)
        completions_map = await task_repo.get_completions_by_task(recurring_ids)

    overdue_lines: list[str] = []
    due_today_lines: list[str] = []
    habit_lines: list[str] = []

    for t in active_tasks:
        if t.recurrence_rule:
            if not is_due_today(t.recurrence_rule, today):
                continue
            done = t.id in completed_today
            dates = completions_map.get(t.id, [])
            mc = missed_count(t.recurrence_rule, dates, today)
            mark = "✓" if done else ("✗" if mc > 0 else "○")
            note = f" ({mc} missed)" if mc > 0 else ""
            habit_lines.append(f"  {mark} {t.title}{note}")
        elif t.deadline and t.deadline < today_start:
            delta = (today_start.date() - t.deadline.date()).days
            overdue_lines.append(f"  - {t.title} ({delta}d overdue)")
        elif t.deadline:
            due_today_lines.append(f"  - {t.title}")

    event_repo = CalendarEventRepository(session)
    events_orm = await event_repo.get_events(
        EventFilters(start_from=today_start, start_to=today_end)
    )
    event_lines: list[str] = []
    for e in sorted(events_orm, key=lambda x: (x.all_day, x.start_datetime)):
        if e.all_day:
            event_lines.append(f"  - {e.title} (all day)")
        else:
            event_lines.append(f"  - {e.title} at {e.start_datetime.strftime('%H:%M')}")

    if not overdue_lines and not due_today_lines and not habit_lines and not event_lines:
        return ""

    parts = [f"## Today — {today.strftime('%A, %B %d')}"]
    if event_lines:
        parts.append("Events:\n" + "\n".join(event_lines))
    if overdue_lines:
        parts.append("Overdue tasks:\n" + "\n".join(overdue_lines))
    if due_today_lines:
        parts.append("Due today:\n" + "\n".join(due_today_lines))
    if habit_lines:
        parts.append("Habits (✓ done  ○ pending  ✗ missed):\n" + "\n".join(habit_lines))

    return "\n".join(parts)
