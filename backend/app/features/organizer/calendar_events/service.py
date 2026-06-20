from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.storage import StorageProvider
from app.features.organizer.calendar_events.tables import CalendarEvent  # noqa: F401 — registers CalendarEvent with SQLAlchemy mapper
from app.features.organizer.calendar_events.schemas import EventCreate, EventUpdate, EventFilters, EventRead
from app.features.organizer.calendar_events.repository import CalendarEventRepository

_OAUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    detail="Google Calendar not authorized. Open GET /integration/google-calendar/oauth/url to start the flow.",
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
        return [EventRead.model_validate(e) for e in events_orm]

    async def create_event(self, event_create: EventCreate) -> EventRead:
        if self._provider is None:
            raise _OAUTH_REQUIRED
        event_record = await self._provider.create(event_create.model_dump(), self._session)
        event_orm = await self._repo.create_event(event_create, event_record["id"])
        return EventRead.model_validate(event_orm)

    async def update_event(self, event_id: int, event_update: EventUpdate) -> EventRead | None:
        if self._provider is None:
            raise _OAUTH_REQUIRED
        event = await self._repo.get_event(event_id)
        if event is None:
            return None
        await self._provider.update(
            event.provider_id,
            event_update.model_dump(exclude_unset=True),
            self._session,
        )
        event_orm = await self._repo.update_event(event_id, event_update)
        return EventRead.model_validate(event_orm)

    async def delete_event(self, event_id: int) -> None:
        if self._provider is None:
            raise _OAUTH_REQUIRED
        event = await self._repo.get_event(event_id)
        if event:
            await self._provider.delete(event.provider_id, self._session)
            await self._repo.delete_event(event_id)
