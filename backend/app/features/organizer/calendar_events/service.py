import logging
from datetime import date, datetime, time
from typing import Any

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
from app.features.organizer.calendar_events.recurrence import end_rule_before, expand_occurrences

logger = logging.getLogger(__name__)

_OAUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Google Calendar not authorized. Open GET /integration/google-calendar/oauth/url to start the flow.",
)
_SYNC_LOOKAHEAD = relativedelta(months=3)

# Planning fields and tags live only in Alfred's DB: they are never sent to Google (the provider
# picks specific keys anyway) and sync() never writes them. An update touching only
# these fields does not need Google, so it works without OAuth and skips the API call.
_ALFRED_ONLY_FIELDS = frozenset({"availability", "presence", "travel_minutes", "routine_id", "tags"})


def _comparable(field: str, value: Any) -> Any:
    if field == "tags":
        return sorted(getattr(tag, "name", tag) for tag in value or [])
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(local_timezone()).replace(tzinfo=None)
    return value


def _changed_fields(event: Any, event_update: EventUpdate) -> dict[str, Any]:
    """Fields of the update that differ from the stored event.

    The portal posts the whole form on every save, so unchanged fields must not count as
    edits: an update that only changes Alfred-only fields never needs Google.
    """
    changed: dict[str, Any] = {}
    for field, value in event_update.model_dump(exclude_unset=True).items():
        if field != "invitees" and _comparable(field, value) == _comparable(field, getattr(event, field)):
            continue
        changed[field] = value
    return changed


def _require_recurring(event: Any) -> None:
    if not event.recurrence_rule:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="This event does not repeat; delete it instead"
        )


def _require_occurrence(event: Any, day: date) -> None:
    _require_recurring(event)
    spans = expand_occurrences(
        event.start_datetime, event.end_datetime, event.recurrence_rule,
        datetime.combine(day, time.min), datetime.combine(day, time.max),
    )
    if not any(start.date() == day for start, _ in spans):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"The event has no occurrence on {day.isoformat()}"
        )


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
            skipped = set(event_read.skips)
            occurrences.extend(
                event_read.model_copy(update={"start_datetime": s, "end_datetime": e})
                for s, e in spans
                if s.date() not in skipped
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
        # The provider converts start/end into the user's local timezone before returning;
        # persist that converted value instead of the caller's raw payload so the naive
        # DB datetime matches what _from_google_event guarantees elsewhere (see sync()).
        converted = event_create.model_copy(update={
            "start_datetime": event_record["start_datetime"],
            "end_datetime": event_record["end_datetime"],
            "timezone": event_record["timezone"],
        })
        event_orm = await self._repo.create_event(converted, event_record["id"])
        logger.info("CalendarEvent created: id=%d title=%r", event_orm.id, event_create.title)
        return EventRead.model_validate(event_orm)

    async def update_event(self, event_id: int, event_update: EventUpdate) -> EventRead | None:
        event = await self._repo.get_event(event_id) if event_update.model_fields_set else None
        if event is not None:
            changed = _changed_fields(event, event_update)
            if set(changed) <= _ALFRED_ONLY_FIELDS:
                return await self._update_alfred_only(event_id, EventUpdate(**changed))
        if self._provider is None:
            logger.warning("CalendarEvent update: Google Calendar not authorized")
            raise _OAUTH_REQUIRED
        event = event or await self._repo.get_event(event_id)
        if event is None:
            logger.debug("CalendarEvent update: id=%d not found", event_id)
            return None
        event_record = await self._provider.update(
            event.provider_id,
            event_update.model_dump(exclude_unset=True),
            self._session,
        )
        # Same timezone-conversion guarantee as create_event: always resync the naive
        # start/end/timezone from the provider's response, even when this update didn't
        # touch them, so previously-uncoverted events self-heal on the next edit.
        converted = event_update.model_copy(update={
            "start_datetime": event_record["start_datetime"],
            "end_datetime": event_record["end_datetime"],
            "timezone": event_record["timezone"],
        })
        event_orm = await self._repo.update_event(event_id, converted)
        logger.info("CalendarEvent updated: id=%d fields=%s", event_id, list(event_update.model_dump(exclude_unset=True).keys()))
        return EventRead.model_validate(event_orm)

    async def _update_alfred_only(self, event_id: int, event_update: EventUpdate) -> EventRead | None:
        event_orm = await self._repo.update_event(event_id, event_update)
        logger.info(
            "CalendarEvent planning fields updated: id=%d fields=%s",
            event_id, list(event_update.model_dump(exclude_unset=True).keys()),
        )
        return EventRead.model_validate(event_orm)

    async def skip_occurrence(self, event_id: int, occurrence_date: date) -> EventRead | None:
        """Leave one occurrence of a recurring event out of every view. Alfred-only: Google is not told."""
        event = await self._repo.get_event(event_id)
        if event is None:
            logger.debug("CalendarEvent skip: id=%d not found", event_id)
            return None
        _require_occurrence(event, occurrence_date)
        if await self._repo.add_skip(event, occurrence_date):
            logger.info("CalendarEvent occurrence skipped: id=%d title=%r date=%s", event_id, event.title, occurrence_date)
        return EventRead.model_validate(event)

    async def unskip_occurrence(self, event_id: int, occurrence_date: date) -> EventRead | None:
        event = await self._repo.get_event(event_id)
        if event is None:
            logger.debug("CalendarEvent unskip: id=%d not found", event_id)
            return None
        if not await self._repo.remove_skip(event, occurrence_date):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{occurrence_date} is not a skipped date of this event"
            )
        logger.info("CalendarEvent occurrence restored: id=%d title=%r date=%s", event_id, event.title, occurrence_date)
        return EventRead.model_validate(event)

    async def end_series(self, event_id: int, from_date: date) -> EventRead | None:
        """Stop a recurring event so its last occurrence is the one before `from_date` (written through to Google)."""
        event = await self._repo.get_event(event_id)
        if event is None:
            logger.debug("CalendarEvent end series: id=%d not found", event_id)
            return None
        _require_recurring(event)
        if from_date <= event.start_datetime.date():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That date is not after the first occurrence; delete the event to remove the whole series",
            )
        remaining = expand_occurrences(
            event.start_datetime, event.end_datetime, event.recurrence_rule,
            datetime.combine(from_date, time.min), None,
        )
        if not remaining:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="The series already ends before that date"
            )
        rule = end_rule_before(event.recurrence_rule, from_date, event.all_day)
        logger.info("CalendarEvent series ended: id=%d title=%r from=%s", event_id, event.title, from_date)
        return await self.update_event(event_id, EventUpdate(recurrence_rule=rule))

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
