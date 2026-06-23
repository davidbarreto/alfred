from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import EventBriefItem, MorningBriefing, TaskBriefItem
from app.shared.weather import WeatherProvider
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters

logger = logging.getLogger(__name__)

_PORTO_TZ = ZoneInfo("Europe/Lisbon")
_ACTIVE_STATUSES = {"TODO", "DOING"}
_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


class BriefingSummaryService:
    def __init__(self, session: AsyncSession, weather_client: WeatherProvider) -> None:
        self._session = session
        self._weather_client = weather_client

    async def build(self) -> MorningBriefing:
        today = datetime.now(_PORTO_TZ).date()
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)

        tasks = await self._fetch_tasks(today_start, today_end)
        events = await self._fetch_events(today_start, today_end)
        weather = await self._weather_client.get_daily_forecast(today)

        return MorningBriefing(date=today, tasks=tasks, events=events, weather=weather)

    async def _fetch_tasks(self, today_start: datetime, today_end: datetime) -> list[TaskBriefItem]:
        repo = TaskRepository(self._session)
        task_filter = TaskFilters(deadline_to=today_end, limit=100)
        raw_tasks = await repo.get_tasks(task_filter)

        items = []
        for task in raw_tasks:
            if task.status not in _ACTIVE_STATUSES:
                continue
            is_overdue = task.deadline is not None and task.deadline < today_start
            items.append(
                TaskBriefItem(
                    id=task.id,
                    title=task.title,
                    priority=task.priority,
                    urgency=task.urgency,
                    deadline=task.deadline,
                    tags=[tag.name for tag in task.tags],
                    is_overdue=is_overdue,
                )
            )

        items.sort(key=lambda t: (not t.is_overdue, _PRIORITY_ORDER.get(t.priority, 99)))
        return items

    async def _fetch_events(self, today_start: datetime, today_end: datetime) -> list[EventBriefItem]:
        repo = CalendarEventRepository(self._session)
        event_filter = EventFilters(start_from=today_start, start_to=today_end)
        raw_events = await repo.get_events(event_filter)

        items = []
        for event in raw_events:
            if event.all_day:
                start_time = "All day"
                end_time = None
            else:
                start_time = event.start_datetime.strftime("%H:%M")
                end_time = event.end_datetime.strftime("%H:%M")

            items.append(
                EventBriefItem(
                    id=event.id,
                    title=event.title,
                    start_time=start_time,
                    end_time=end_time,
                    location=event.location,
                    description=event.description,
                    all_day=event.all_day,
                )
            )

        items.sort(key=lambda e: (e.all_day, e.start_time))
        return items
