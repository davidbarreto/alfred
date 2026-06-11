import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventCreate, EventUpdate, EventFilters
import app.features.organizer.tasks.tables  # noqa: F401 — registers Task with SQLAlchemy mapper
import app.features.organizer.notes.tables  # noqa: F401 — registers Note with SQLAlchemy mapper


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _make_event_orm(id=1, **kwargs):
    event = MagicMock()
    event.id = id
    event.title = kwargs.get("title", "Team Sync")
    event.description = kwargs.get("description", None)
    event.location = kwargs.get("location", None)
    event.start_datetime = kwargs.get("start_datetime", datetime(2026, 6, 15, 10, 0))
    event.end_datetime = kwargs.get("end_datetime", datetime(2026, 6, 15, 11, 0))
    event.all_day = kwargs.get("all_day", False)
    event.recurrence_rule = kwargs.get("recurrence_rule", None)
    event.host = kwargs.get("host", None)
    event.invitees = kwargs.get("invitees", [])
    event.tags = kwargs.get("tags", [])
    event.provider_id = kwargs.get("provider_id", "gc-event-1")
    return event


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _scalar_one(value):
    result = MagicMock()
    result.scalars.return_value.one.return_value = value
    return result


_START = datetime(2026, 6, 15, 10, 0)
_END = datetime(2026, 6, 15, 11, 0)


class TestGetEvent:
    async def test_found(self):
        session = _make_session()
        event = _make_event_orm()
        session.execute.return_value = _scalar_first(event)

        repo = CalendarEventRepository(session)
        result = await repo.get_event(1)

        assert result == event
        session.execute.assert_called_once()

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = CalendarEventRepository(session)
        result = await repo.get_event(999)

        assert result is None


class TestGetEvents:
    async def test_returns_list(self):
        session = _make_session()
        events = [_make_event_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(events)

        repo = CalendarEventRepository(session)
        result = await repo.get_events(EventFilters())

        assert len(result) == 3
        session.execute.assert_called_once()

    async def test_empty_list(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = CalendarEventRepository(session)
        result = await repo.get_events(EventFilters())
        assert result == []

    async def test_start_from_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = CalendarEventRepository(session)
        await repo.get_events(EventFilters(start_from=datetime(2026, 6, 1)))
        session.execute.assert_called_once()

    async def test_start_to_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = CalendarEventRepository(session)
        await repo.get_events(EventFilters(start_to=datetime(2026, 6, 30)))
        session.execute.assert_called_once()

    async def test_tags_filter_applied(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])

        repo = CalendarEventRepository(session)
        await repo.get_events(EventFilters(tags=["work"]))
        session.execute.assert_called_once()


class TestCreateEvent:
    async def test_create_with_no_tags_or_invitees(self):
        session = _make_session()
        event = _make_event_orm()
        session.execute.return_value = _scalar_one(event)

        repo = CalendarEventRepository(session)
        result = await repo.create_event(
            EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END),
            "gc-event-1",
        )

        session.add.assert_called()
        session.commit.assert_called_once()
        assert result == event

    async def test_create_with_invitees(self):
        session = _make_session()
        event = _make_event_orm()
        session.execute.return_value = _scalar_one(event)

        repo = CalendarEventRepository(session)
        result = await repo.create_event(
            EventCreate(
                title="Stand-up",
                start_datetime=_START,
                end_datetime=_END,
                invitees=["alice@example.com", "bob@example.com"],
            ),
            "gc-event-1",
        )

        session.add.assert_called()
        session.commit.assert_called_once()
        assert result == event

    async def test_create_with_host(self):
        session = _make_session()
        event = _make_event_orm(host="organizer@example.com")
        session.execute.return_value = _scalar_one(event)

        repo = CalendarEventRepository(session)
        result = await repo.create_event(
            EventCreate(
                title="Stand-up",
                start_datetime=_START,
                end_datetime=_END,
                host="organizer@example.com",
            ),
            "gc-event-1",
        )

        session.commit.assert_called_once()
        assert result == event

    async def test_create_with_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing_tag = Tag(name="work", provider_id="gc-event-1")
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(existing_tag), _scalar_one(event)]

        repo = CalendarEventRepository(session)
        result = await repo.create_event(
            EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END, tags=["work"]),
            "gc-event-1",
        )

        session.commit.assert_called_once()
        assert result == event

    async def test_create_with_new_tag(self):
        session = _make_session()
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(None), _scalar_one(event)]

        repo = CalendarEventRepository(session)
        result = await repo.create_event(
            EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END, tags=["newtag"]),
            "gc-event-1",
        )

        session.commit.assert_called_once()
        assert session.add.call_count >= 2
        assert result == event


class TestUpdateEvent:
    async def test_update_found(self):
        session = _make_session()
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(event), _scalar_one(event)]

        repo = CalendarEventRepository(session)
        result = await repo.update_event(1, EventUpdate(title="Updated"))

        session.commit.assert_called_once()
        assert result == event

    async def test_update_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = CalendarEventRepository(session)
        result = await repo.update_event(999, EventUpdate(title="X"))

        assert result is None
        session.commit.assert_not_called()

    async def test_update_invitees(self):
        session = _make_session()
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(event), _scalar_one(event)]

        repo = CalendarEventRepository(session)
        result = await repo.update_event(
            1, EventUpdate(invitees=["new@example.com"])
        )

        session.commit.assert_called_once()
        assert result == event

    async def test_update_host(self):
        session = _make_session()
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(event), _scalar_one(event)]

        repo = CalendarEventRepository(session)
        result = await repo.update_event(1, EventUpdate(host="new-host@example.com"))

        session.commit.assert_called_once()
        assert result == event

    async def test_update_resolves_tags(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        event = _make_event_orm(provider_id="gc-event-1")
        existing_tag = Tag(name="work", provider_id="gc-event-1")

        session.execute.side_effect = [
            _scalar_first(event),
            _scalar_first(existing_tag),
            _scalar_one(event),
        ]

        repo = CalendarEventRepository(session)
        result = await repo.update_event(1, EventUpdate(tags=["work"]))

        session.commit.assert_called_once()
        assert result == event


class TestDeleteEvent:
    async def test_delete_found(self):
        session = _make_session()
        event = _make_event_orm()

        session.execute.side_effect = [_scalar_first(event), MagicMock()]

        repo = CalendarEventRepository(session)
        await repo.delete_event(1)

        session.commit.assert_called_once()

    async def test_delete_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = CalendarEventRepository(session)
        result = await repo.delete_event(999)

        assert result is None
        session.commit.assert_not_called()


class TestResolveTags:
    async def test_returns_existing_tag(self):
        session = _make_session()
        from app.features.organizer.tags.tables import Tag
        existing_tag = Tag(name="work", provider_id="gc-event-1")
        session.execute.return_value = _scalar_first(existing_tag)

        repo = CalendarEventRepository(session)
        tags = await repo._resolve_tags(["work"], "gc-event-1")

        assert len(tags) == 1
        assert tags[0] is existing_tag
        session.add.assert_not_called()

    async def test_creates_new_tag(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = CalendarEventRepository(session)
        tags = await repo._resolve_tags(["newtag"], "gc-event-1")

        assert len(tags) == 1
        session.add.assert_called_once()

    async def test_empty_tags_list(self):
        session = _make_session()
        repo = CalendarEventRepository(session)
        tags = await repo._resolve_tags([], "gc-event-1")
        assert tags == []
        session.execute.assert_not_called()
