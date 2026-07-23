from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import BirthdayItem, EventBriefItem, HolidayItem, LanguageBriefItem, MorningBriefing, RecurringBriefItem, ShoppingBriefItem, TaskBriefItem, WeatherForecast
from app.features.language.chunks.repository import ChunkRepository
from app.features.language.sessions.repository import SessionRepository as LanguageSessionRepository
from app.features.language.tracks.repository import TrackRepository as LanguageTrackRepository
from app.features.language.tracks.schemas import TrackFilters as LanguageTrackFilters
from app.features.organizer.calendar_events.schemas import EventFilters
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.contacts.service import ContactService
from app.features.organizer.shopping.recurrence import is_recurrence_due
from app.features.organizer.shopping.repository import RecurrenceRepository, ShoppingRepository
from app.features.organizer.shopping.schemas import ShoppingItemFilters
from app.features.organizer.shopping_categories.repository import ShoppingCategoryRepository
from app.features.organizer.tasks.recurrence import is_done_in_cycle, is_due_today
from app.features.organizer.tasks.repository import TaskRepository
from app.features.organizer.tasks.schemas import TaskFilters
from app.shared.holiday import HolidayProvider
from app.shared.timezone import local_now
from app.shared.weather import WeatherProvider

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {"TODO", "DOING"}
_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_HOLIDAY_LOOKAHEAD_DAYS = 7
_LOOKAHEAD_DAYS = 3


class MorningBriefingSummaryService:
    def __init__(
        self,
        session: AsyncSession,
        weather_client: WeatherProvider,
        holiday_client: HolidayProvider | None,
        contact_service: ContactService | None,
    ) -> None:
        self._session = session
        self._weather_client = weather_client
        self._holiday_client = holiday_client
        self._contact_service = contact_service

    async def build(self) -> MorningBriefing:
        today = local_now().date()
        today_start = datetime.combine(today, time.min)
        today_end = datetime.combine(today, time.max)
        lookahead_end = datetime.combine(today + timedelta(days=_LOOKAHEAD_DAYS - 1), time.max)

        holiday_window_end = today + timedelta(days=_HOLIDAY_LOOKAHEAD_DAYS)

        # These all share a single AsyncSession, which SQLAlchemy does not
        # support using concurrently, so they must run sequentially. Weather
        # and holidays now also log to that same session (provider_calls),
        # so they've moved into this sequential run too -- each still
        # degrades to an empty result on failure instead of failing the
        # whole briefing.
        tasks = await self._fetch_tasks(today, today_start, today_end, lookahead_end)
        events = await self._fetch_events(today, today_start, lookahead_end)
        birthdays = await self._fetch_birthdays(today)
        language = await self._fetch_language()
        shopping = await self._fetch_shopping()
        recurring = await self._fetch_recurring()
        weather = await self._fetch_weather(today)
        holidays = await self._fetch_holidays(today, holiday_window_end)

        return MorningBriefing(
            date=today,
            lookahead_days=_LOOKAHEAD_DAYS,
            tasks=tasks,
            events=events,
            weather=weather,
            holidays=holidays,
            birthdays=birthdays,
            language=language,
            shopping=shopping,
            recurring=recurring,
        )

    async def _fetch_tasks(
        self, today: date, today_start: datetime, today_end: datetime, lookahead_end: datetime
    ) -> list[TaskBriefItem]:
        repo = TaskRepository(self._session)
        task_filter = TaskFilters(deadline_to=lookahead_end, include_recurring=True, limit=100)
        raw_tasks = await repo.get_tasks(task_filter)

        recurring_ids = [t.id for t in raw_tasks if t.recurrence_rule is not None]
        completions_map = (
            await repo.get_completions_by_task(recurring_ids) if recurring_ids else {}
        )

        items = []
        for task in raw_tasks:
            if task.status not in _ACTIVE_STATUSES:
                continue
            if task.recurrence_rule is not None:
                dates = completions_map.get(task.id, [])
                if not is_due_today(task.recurrence_rule, today) or is_done_in_cycle(
                    task.recurrence_rule, dates, today
                ):
                    continue
            is_overdue = task.deadline is not None and task.deadline < today_start
            # Recurring tasks have no deadline, but reaching this point already means
            # is_due_today matched -- so they belong in the "today" bucket, not "upcoming".
            is_today = task.recurrence_rule is not None or (
                task.deadline is not None and today_start <= task.deadline <= today_end
            )
            items.append(
                TaskBriefItem(
                    id=task.id,
                    title=task.title,
                    priority=task.priority,
                    urgency=task.urgency,
                    deadline=task.deadline,
                    tags=[tag.name for tag in task.tags],
                    is_overdue=is_overdue,
                    is_today=is_today,
                )
            )

        items.sort(
            key=lambda t: (
                not t.is_overdue,
                not t.is_today,
                t.deadline or datetime.max,
                _PRIORITY_ORDER.get(t.priority, 99),
            )
        )
        return items

    async def _fetch_events(self, today: date, today_start: datetime, lookahead_end: datetime) -> list[EventBriefItem]:
        service = CalendarEventService(provider=None, session=self._session)
        event_filter = EventFilters(start_from=today_start, start_to=lookahead_end)
        raw_events = await service.get_events(event_filter)

        items = []
        for event in raw_events:
            event_date = event.start_datetime.date()
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
                    date=event_date,
                    start_time=start_time,
                    end_time=end_time,
                    location=event.location,
                    description=event.description,
                    all_day=event.all_day,
                    is_today=event_date == today,
                    days_until=(event_date - today).days,
                )
            )

        items.sort(key=lambda e: (not e.is_today, e.date, e.all_day, e.start_time))
        return items

    async def _fetch_language(self) -> list[LanguageBriefItem]:
        track_repo = LanguageTrackRepository(self._session)
        chunk_repo = ChunkRepository(self._session)
        session_repo = LanguageSessionRepository(self._session)

        tracks = await track_repo.get_tracks(LanguageTrackFilters(active_only=True))
        items = []
        for track in tracks:
            due_count = await chunk_repo.count_due_for_track(track.id)
            completed_today = await session_repo.count_srs_reviews_today(track.id)
            quota_met = completed_today >= track.daily_quota
            items.append(LanguageBriefItem(
                track_id=track.id,
                code=track.code,
                name=track.name,
                due_count=due_count,
                completed_today=completed_today,
                daily_quota=track.daily_quota,
                quota_met=quota_met,
            ))
        return items

    async def _fetch_shopping(self) -> list[ShoppingBriefItem]:
        repo = ShoppingRepository(self._session)
        category_repo = ShoppingCategoryRepository(self._session)
        raw_items = await repo.list(ShoppingItemFilters(status="pending"))
        categories = {c.id: c.name for c in await category_repo.list()}
        return [
            ShoppingBriefItem(
                id=item.id,
                name=item.name,
                category=categories.get(item.category_id, "other"),
                priority=item.priority,
                quantity=float(item.quantity) if item.quantity is not None else None,
                unit=item.unit,
                store=item.store,
            )
            for item in raw_items
        ]

    async def _fetch_recurring(self) -> list[RecurringBriefItem]:
        repo = RecurrenceRepository(self._session)
        items = await repo.list(active_only=True)
        due = [item for item in items if is_recurrence_due(item.last_added_at, item.recurrence_days)]
        return [RecurringBriefItem(id=item.id, name=item.name) for item in due]

    async def _fetch_birthdays(self, today: date) -> list[BirthdayItem]:
        if self._contact_service is None:
            return []
        raw = await self._contact_service.get_upcoming_birthdays(today)
        return [
            BirthdayItem(name=r["name"], days_until=r["days_until"], date=r["date"], is_self=r.get("is_self", False))
            for r in raw
        ]

    async def _fetch_weather(self, today: date) -> WeatherForecast | None:
        try:
            return await self._weather_client.get_daily_forecast(today, session=self._session)
        except Exception:
            logger.warning("Failed to fetch weather forecast", exc_info=True)
            return None

    async def _fetch_holidays(self, today: date, window_end: date) -> list[HolidayItem]:
        if self._holiday_client is None:
            return []
        try:
            return await self._holiday_client.get_holidays(today, window_end, session=self._session)
        except Exception:
            logger.warning("Failed to fetch holidays", exc_info=True)
            return []
