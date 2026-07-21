import logging
from datetime import date, datetime, time

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.shared.timezone import local_now, local_timezone
from app.features.organizer.calendar_events.tables import CalendarEvent  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper
from app.features.organizer.calendar_events.schemas import (
    CalendarSyncResult,
    EventCreate,
    EventUpdate,
    EventFilters,
    EventRead,
)
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.recurrence import expand_occurrences

logger = logging.getLogger(__name__)

_OAUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Google Calendar not authorized. Open GET /integration/google-calendar/oauth/url to start the flow.",
)
_SYNC_LOOKAHEAD = relativedelta(months=3)


class CalendarEventService:

    def __init__(self, provider: StorageProvider | None, session: AsyncSession) -> None:
        self._provider = provider
        self._session = session
        self._repo = CalendarEventRepository(session)

    async def get_event(self, event_id: int) -> EventRead | None:
        event_orm = await self._repo.get_event(event_id)
        if event_orm is None:
            return None
        return EventRead.model_validate(event_orm)

    async def get_events(self, filters: EventFilters) -> list[EventRead]:
        events_orm = await self._repo.get_events(filters)
        occurrences: list[EventRead] = []
        for event_orm in events_orm:
            event_read = EventRead.model_validate(event_orm)
            if not event_read.recurrence_rule:
                occurrences.append(event_read)
                continue
            try:
                spans = expand_occurrences(
                    event_read.start_datetime,
                    event_read.end_datetime,
                    event_read.recurrence_rule,
                    filters.start_from,
                    filters.start_to,
                )
            except (ValueError, OverflowError) as exc:
                logger.warning(
                    "CalendarEvent recurrence expansion failed: id=%d rule=%r error=%s",
                    event_read.id, event_read.recurrence_rule, exc,
                )
                occurrences.append(event_read)
                continue
            occurrences.extend(
                event_read.model_copy(update={"start_datetime": s, "end_datetime": e})
                for s, e in spans
            )
        occurrences.sort(key=lambda e: e.start_datetime)
        return occurrences

    async def sync(self, start: date | None = None, end: date | None = None) -> CalendarSyncResult:
        if self._provider is None:
            logger.warning("CalendarEvent sync: Google Calendar not authorized")
            raise _OAUTH_REQUIRED

        sync_start = start or local_now().date()
        sync_end = end or sync_start + _SYNC_LOOKAHEAD
        start_dt = datetime.combine(sync_start, time.min, tzinfo=local_timezone())
        end_dt = datetime.combine(sync_end, time.min, tzinfo=local_timezone())

        records = await self._provider.list(
            {"start_from": start_dt, "start_to": end_dt}, self._session
        )

        created = 0
        updated = 0
        for record in records:
            provider_id = record.pop("id")
            existing = await self._repo.get_event_by_provider_id(provider_id)
            if existing is not None:
                await self._repo.update_event(existing.id, EventUpdate(**record))
                updated += 1
            else:
                await self._repo.create_event(EventCreate(**record), provider_id)
                created += 1

        logger.info(
            "CalendarEvent sync: start=%s end=%s created=%d updated=%d",
            sync_start, sync_end, created, updated,
        )
        return CalendarSyncResult(created=created, updated=updated, start=sync_start, end=sync_end)

    async def create_event(self, event_create: EventCreate) -> EventRead:
        if self._provider is None:
            logger.warning("CalendarEvent create: Google Calendar not authorized")
            raise _OAUTH_REQUIRED
        event_record = await self._provider.create(event_create.model_dump(), self._session)
        event_orm = await self._repo.create_event(event_create, event_record["id"])
        logger.info("CalendarEvent created: id=%d title=%r", event_orm.id, event_create.title)
        return EventRead.model_validate(event_orm)

    async def update_event(self, event_id: int, event_update: EventUpdate) -> EventRead | None:
        if self._provider is None:
            logger.warning("CalendarEvent update: Google Calendar not authorized")
            raise _OAUTH_REQUIRED
        event = await self._repo.get_event(event_id)
        if event is None:
            logger.debug("CalendarEvent update: id=%d not found", event_id)
            return None
        await self._provider.update(
            event.provider_id,
            event_update.model_dump(exclude_unset=True),
            self._session,
        )
        event_orm = await self._repo.update_event(event_id, event_update)
        logger.info("CalendarEvent updated: id=%d fields=%s", event_id, list(event_update.model_dump(exclude_unset=True).keys()))
        return EventRead.model_validate(event_orm)

    async def delete_event(self, event_id: int) -> None:
        if self._provider is None:
            logger.warning("CalendarEvent delete: Google Calendar not authorized")
            raise _OAUTH_REQUIRED
        event = await self._repo.get_event(event_id)
        if event:
            await self._provider.delete(event.provider_id, self._session)
            await self._repo.delete_event(event_id)
            logger.info("CalendarEvent deleted: id=%d", event_id)
        else:
            logger.debug("CalendarEvent delete: id=%d not found", event_id)
