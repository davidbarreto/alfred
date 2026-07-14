from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession


def _naive_utc(dt: object) -> object:
    from datetime import datetime
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt

from app.features.organizer.tags.tables import Tag
from app.features.organizer.calendar_events.tables import CalendarEvent, CalendarEventInvitee
from app.features.organizer.calendar_events.schemas import EventCreate, EventUpdate, EventFilters

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

    async def get_events(self, event_filter: EventFilters) -> list[CalendarEvent]:
        query = select(CalendarEvent).options(
            selectinload(CalendarEvent.tags), selectinload(CalendarEvent.invitees)
        )
        if event_filter.start_from is not None:
            query = query.where(CalendarEvent.start_datetime >= _naive_utc(event_filter.start_from))
        if event_filter.start_to is not None:
            query = query.where(CalendarEvent.start_datetime <= _naive_utc(event_filter.start_to))
        if event_filter.tags:
            query = query.where(CalendarEvent.tags.any(Tag.name.in_(event_filter.tags)))
        query = query.order_by(CalendarEvent.start_datetime.asc()).limit(event_filter.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def _resolve_tags(self, tag_names: list[str], provider_id: str) -> list[Tag]:
        tags = []
        for name in tag_names:
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
