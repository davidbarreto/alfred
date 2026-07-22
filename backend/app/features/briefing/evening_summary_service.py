from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import EveningDigest, EveningEventItem, EveningNoteItem, EveningTaskItem, WinItem
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.notes.repository import NoteRepository
from app.features.organizer.notes.schemas import NoteFilters
from app.features.organizer.tasks.ranking import task_priority_sort_key
from app.features.organizer.tasks.recurrence import is_done_in_cycle, is_due_today
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters
from app.shared.timezone import local_now

_NOTES_CONTEXT_LIMIT = 15


class EveningDigestSummaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def build(self) -> EveningDigest:
        now = local_now().replace(tzinfo=None)
        today = now.date()
        tomorrow = today + timedelta(days=1)

        wins, tasks = await self._collect_wins_and_tasks(today, now)
        tomorrow_events = await self._fetch_tomorrow_events(tomorrow)
        notes = await self._fetch_notes()

        return EveningDigest(date=today, wins=wins, tasks=tasks, tomorrow_events=tomorrow_events, notes=notes)

    async def _collect_wins_and_tasks(
        self, today: date, now: datetime
    ) -> tuple[list[WinItem], list[EveningTaskItem]]:
        repo = TaskRepository(self._session)
        active_orm = await repo.get_tasks(TaskFilters(status="ACTIVE", limit=100))

        recurring_ids = [t.id for t in active_orm if t.recurrence_rule is not None]
        completed_recurring_ids = (
            await repo.get_completed_task_ids_for_date(recurring_ids, today) if recurring_ids else set()
        )
        completions_map = (
            await repo.get_completions_by_task(recurring_ids) if recurring_ids else {}
        )
        wins = [WinItem(title=t.title) for t in active_orm if t.id in completed_recurring_ids]

        done_today = await repo.get_tasks_completed_on(today)
        wins.extend(WinItem(title=t.title) for t in done_today)

        tasks = [
            EveningTaskItem(
                id=t.id,
                title=t.title,
                priority=t.priority,
                urgency=t.urgency,
                deadline=t.deadline,
                tags=[tag.name for tag in t.tags],
                is_overdue=t.deadline is not None and t.deadline < now,
            )
            for t in active_orm
            if t.recurrence_rule is None
            or (
                is_due_today(t.recurrence_rule, today)
                and not is_done_in_cycle(t.recurrence_rule, completions_map.get(t.id, []), today)
            )
        ]
        tasks.sort(key=lambda item: task_priority_sort_key(item, now))
        return wins, tasks

    async def _fetch_tomorrow_events(self, tomorrow: date) -> list[EveningEventItem]:
        service = CalendarEventService(provider=None, session=self._session)
        start = datetime.combine(tomorrow, time.min)
        end = datetime.combine(tomorrow, time.max)
        events = await service.get_events(EventFilters(start_from=start, start_to=end, limit=20))

        items = []
        for event in events:
            if event.all_day:
                start_time, end_time = "All day", None
            else:
                start_time, end_time = event.start_datetime.strftime("%H:%M"), event.end_datetime.strftime("%H:%M")
            items.append(
                EveningEventItem(
                    id=event.id,
                    title=event.title,
                    date=event.start_datetime.date(),
                    start_time=start_time,
                    end_time=end_time,
                    location=event.location,
                    all_day=event.all_day,
                )
            )
        return items

    async def _fetch_notes(self) -> list[EveningNoteItem]:
        repo = NoteRepository(self._session)
        notes = await repo.get_notes(NoteFilters(limit=_NOTES_CONTEXT_LIMIT))
        return [EveningNoteItem(id=n.id, title=n.title, content=n.content) for n in notes]
