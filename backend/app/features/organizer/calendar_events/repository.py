from datetime import date, datetime

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession


def _naive_utc(dt: object) -> object:
    from datetime import datetime
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

from app.features.organizer.tags.tables import Tag
from app.features.organizer.calendar_events.tables import (
    CalendarEvent, CalendarEventInvitee, CalendarEventOverride, CalendarEventSkip,
)
from app.features.organizer.calendar_events.schemas import EventCreate, EventUpdate, EventFilters
from app.shared.tags import normalize_tag_name

_EVENT_EXCLUDE = {"tags", "invitees"}


class CalendarEventRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event(self, event_id: int) -> CalendarEvent | None:
        result = await self._session.execute(
            select(CalendarEvent)
            .options(selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees))
            .where(CalendarEvent.id == event_id)
        )
        return result.scalars().first()

    async def get_event_by_provider_id(self, provider_id: str) -> CalendarEvent | None:
        result = await self._session.execute(
            select(CalendarEvent)
            .options(selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees))
            .where(CalendarEvent.provider_id == provider_id)
        )
        return result.scalars().first()

    async def get_events(self, event_filter: EventFilters) -> list[CalendarEvent]:
        query = select(CalendarEvent).options(
            selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees)
        )
        start_from = _naive_utc(event_filter.start_from)
        start_to = _naive_utc(event_filter.start_to)
        if start_from is not None or start_to is not None:
            # A recurring series' own start_datetime can predate the queried range while
            # still producing occurrences inside it, so it can't be filtered by start_datetime
            # alone — only bound it by start_to; occurrence expansion happens in the service.
            non_recurring_range = [CalendarEvent.recurrence_rule.is_(None)]
            if start_from is not None:
                non_recurring_range.append(CalendarEvent.start_datetime >= start_from)
            if start_to is not None:
                non_recurring_range.append(CalendarEvent.start_datetime <= start_to)

            recurring_range = [CalendarEvent.recurrence_rule.isnot(None)]
            if start_to is not None:
                recurring_range.append(CalendarEvent.start_datetime <= start_to)

            query = query.where(or_(and_(*non_recurring_range), and_(*recurring_range)))
        if event_filter.tags:
            query = query.where(CalendarEvent.tags.any(Tag.name.in_(map(normalize_tag_name, event_filter.tags))))
        if event_filter.q:
            query = query.where(CalendarEvent.title.ilike(f"%{event_filter.q}%"))
        query = query.order_by(CalendarEvent.start_datetime.asc()).limit(event_filter.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, tag_names: list[str], provider_id: str) -> list[Tag]:
        tags = []
        for name in map(normalize_tag_name, tag_names):
            result = await self._session.execute(
                select(Tag).where(Tag.provider_id == provider_id, Tag.name == name)
            )
            tag = result.scalars().first()
            if tag is None:
                tag = Tag(provider_id=provider_id, name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags

    async def create_event(self, event_create: EventCreate, provider_id: str) -> CalendarEvent:
        event = CalendarEvent(
            **event_create.model_dump(exclude=_EVENT_EXCLUDE),
            provider_id=provider_id,
        )
        event.tags = await self._resolve_tags(event_create.tags, provider_id)
        event.invitees = [CalendarEventInvitee(email=e) for e in event_create.invitees]
        self._session.add(event)
        await self._session.commit()
        result = await self._session.execute(
            select(CalendarEvent)
            .options(selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees))
            .where(CalendarEvent.id == event.id)
        )
        return result.scalars().one()

    async def update_event(self, event_id: int, event_update: EventUpdate) -> CalendarEvent | None:
        event = await self.get_event(event_id)
        if event is None:
            return None

        update_data = event_update.model_dump(exclude_unset=True)
        if "tags" in update_data:
            event.tags = await self._resolve_tags(update_data.pop("tags"), event.provider_id)
        if "invitees" in update_data:
            event.invitees = [CalendarEventInvitee(email=e) for e in update_data.pop("invitees")]

        for field, value in update_data.items():
            setattr(event, field, value)

        await self._session.commit()
        result = await self._session.execute(
            select(CalendarEvent)
            .options(selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees))
            .where(CalendarEvent.id == event_id)
        )
        return result.scalars().one()

    async def delete_event(self, event_id: int) -> None:
        event = await self.get_event(event_id)
        if event is None:
            return None
        await self._session.execute(delete(CalendarEvent).where(CalendarEvent.id == event_id))
        await self._session.commit()

    async def add_skip(self, event: CalendarEvent, occurrence_date: date) -> bool:
        """Record a skipped occurrence on the loaded event; False when it was already skipped."""
        if any(skip.occurrence_date == occurrence_date for skip in event.skips):
            return False
        event.skips.append(CalendarEventSkip(occurrence_date=occurrence_date))
        await self._session.commit()
        return True

    async def remove_skip(self, event: CalendarEvent, occurrence_date: date) -> bool:
        """Forget a skipped occurrence on the loaded event; False when it was not skipped."""
        for skip in event.skips:
            if skip.occurrence_date == occurrence_date:
                event.skips.remove(skip)
                await self._session.commit()
                return True
        return False

    async def set_override(self, event: CalendarEvent, occurrence_date: date, start: datetime, end: datetime) -> None:
        """Move one occurrence of the loaded event: updates its override, or creates it."""
        for override in event.overrides:
            if override.occurrence_date == occurrence_date:
                override.start_datetime, override.end_datetime = start, end
                break
        else:
            event.overrides.append(
                CalendarEventOverride(occurrence_date=occurrence_date, start_datetime=start, end_datetime=end)
            )
        await self._session.commit()

    async def remove_override(self, event: CalendarEvent, occurrence_date: date) -> bool:
        """Put one occurrence back at its series time; False when it was not moved."""
        for override in event.overrides:
            if override.occurrence_date == occurrence_date:
                event.overrides.remove(override)
                await self._session.commit()
                return True
        return False

    async def remove_overrides_from(self, event: CalendarEvent, from_date: date) -> None:
        """Forget the overrides of occurrences on or after `from_date` (the series no longer has them)."""
        stale = [o for o in event.overrides if o.occurrence_date >= from_date]
        for override in stale:
            event.overrides.remove(override)
        if stale:
            await self._session.commit()
