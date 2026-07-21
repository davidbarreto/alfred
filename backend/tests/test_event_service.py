import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.calendar_events.schemas import EventCreate, EventUpdate, EventFilters, EventRead

_START = datetime(2026, 6, 15, 10, 0)
_END = datetime(2026, 6, 15, 11, 0)


def _make_event_read(**kwargs):
    defaults = dict(
        id=1,
        title="Team Sync",
        description=None,
        location=None,
        start_datetime=_START,
        end_datetime=_END,
        all_day=False,
        host=None,
        invitees=[],
        tags=[],
        recurrence_rule=None,
    )
    defaults.update(kwargs)
    return EventRead(**defaults)


def _make_event_orm(**kwargs):
    event = MagicMock()
    event.id = kwargs.get("id", 1)
    event.title = kwargs.get("title", "Team Sync")
    event.description = kwargs.get("description", None)
    event.location = kwargs.get("location", None)
    event.start_datetime = kwargs.get("start_datetime", _START)
    event.end_datetime = kwargs.get("end_datetime", _END)
    event.all_day = kwargs.get("all_day", False)
    event.recurrence_rule = kwargs.get("recurrence_rule", None)
    event.host = kwargs.get("host", None)
    event.invitees = kwargs.get("invitees", [])
    event.tags = kwargs.get("tags", [])
    event.timezone = kwargs.get("timezone", None)
    event.provider_id = kwargs.get("provider_id", "gc-event-1")
    return event


@pytest.fixture
def mock_provider():
    return AsyncMock()


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def service(mock_provider, mock_session):
    svc = CalendarEventService(provider=mock_provider, session=mock_session)
    svc._repo = AsyncMock()
    return svc



class TestGetEvent:
    async def test_returns_event_read_when_found(self, service):
        service._repo.get_event.return_value = _make_event_orm()

        result = await service.get_event(1)

        service._repo.get_event.assert_called_once_with(1)
        assert result is not None
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_event.return_value = None

        result = await service.get_event(999)
        assert result is None

    async def test_returns_event_read_type(self, service):
        service._repo.get_event.return_value = _make_event_orm()
        result = await service.get_event(1)
        assert isinstance(result, EventRead)


class TestGetEvents:
    async def test_returns_list_of_event_reads(self, service):
        service._repo.get_events.return_value = [_make_event_orm(id=i) for i in range(3)]

        result = await service.get_events(EventFilters())

        assert len(result) == 3
        assert all(isinstance(e, EventRead) for e in result)

    async def test_empty_list(self, service):
        service._repo.get_events.return_value = []
        result = await service.get_events(EventFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.get_events.return_value = []
        filters = EventFilters(tags=["work"], start_from=_START)
        await service.get_events(filters)
        service._repo.get_events.assert_called_once_with(filters)

    async def test_expands_recurring_event_into_occurrences_within_range(self, service):
        service._repo.get_events.return_value = [
            _make_event_orm(recurrence_rule="FREQ=WEEKLY")
        ]
        filters = EventFilters(
            start_from=datetime(2026, 7, 1), start_to=datetime(2026, 7, 31, 23, 59, 59)
        )

        result = await service.get_events(filters)

        assert len(result) == 4  # 2026-06-15 weekly -> four Mondays in July
        assert all(e.id == 1 for e in result)
        assert [e.start_datetime.date().isoformat() for e in result] == [
            "2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27",
        ]

    async def test_recurring_event_outside_range_is_dropped(self, service):
        service._repo.get_events.return_value = [
            _make_event_orm(recurrence_rule="FREQ=WEEKLY;COUNT=2")
        ]
        filters = EventFilters(
            start_from=datetime(2026, 12, 1), start_to=datetime(2026, 12, 31)
        )

        result = await service.get_events(filters)

        assert result == []

    async def test_non_recurring_event_unaffected(self, service):
        service._repo.get_events.return_value = [_make_event_orm(recurrence_rule=None)]

        result = await service.get_events(EventFilters())

        assert len(result) == 1
        assert result[0].start_datetime == _START

    async def test_invalid_recurrence_rule_falls_back_to_master_event(self, service):
        service._repo.get_events.return_value = [
            _make_event_orm(recurrence_rule="NOT-A-VALID-RRULE")
        ]

        result = await service.get_events(EventFilters())

        assert len(result) == 1
        assert result[0].start_datetime == _START


def _provider_record(provider_id: str, **kwargs) -> dict:
    defaults = dict(
        id=provider_id,
        start_datetime=_START,
        end_datetime=_END,
        timezone=None,
    )
    defaults.update(kwargs)
    return defaults


class TestCreateEvent:
    async def test_calls_provider_create(self, service, mock_provider):
        event_create = EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END)
        mock_provider.create.return_value = _provider_record("gc-abc")
        service._repo.create_event.return_value = _make_event_orm(title="Stand-up")

        await service.create_event(event_create)

        mock_provider.create.assert_called_once()

    async def test_calls_repo_create_with_provider_id(self, service, mock_provider):
        event_create = EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END)
        mock_provider.create.return_value = _provider_record("gc-xyz")
        service._repo.create_event.return_value = _make_event_orm()

        await service.create_event(event_create)

        # Provider echoed back the same start/end/timezone, so the persisted
        # event is value-equal to the caller's original payload.
        service._repo.create_event.assert_called_once_with(event_create, "gc-xyz")

    async def test_returns_event_read(self, service, mock_provider):
        mock_provider.create.return_value = _provider_record("gc-1")
        service._repo.create_event.return_value = _make_event_orm()

        result = await service.create_event(
            EventCreate(title="Stand-up", start_datetime=_START, end_datetime=_END)
        )
        assert isinstance(result, EventRead)


class TestUpdateEvent:
    async def test_returns_updated_event(self, service, mock_provider):
        service._repo.get_event.return_value = _make_event_orm()
        service._repo.update_event.return_value = _make_event_orm(title="Updated")
        mock_provider.update.return_value = _provider_record("gc-event-1")
        event_update = EventUpdate(title="Updated")

        result = await service.update_event(1, event_update)

        # The provider always reports the event's true current start/end/timezone,
        # which the service persists alongside the requested field(s).
        service._repo.update_event.assert_called_once_with(
            1, EventUpdate(title="Updated", start_datetime=_START, end_datetime=_END, timezone=None)
        )
        assert isinstance(result, EventRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_event.return_value = None
        result = await service.update_event(999, EventUpdate(title="X"))
        assert result is None

    async def test_calls_provider_update(self, service, mock_provider):
        event_orm = _make_event_orm(provider_id="gc-abc")
        service._repo.get_event.return_value = event_orm
        service._repo.update_event.return_value = event_orm
        event_update = EventUpdate(title="Updated")

        await service.update_event(1, event_update)

        mock_provider.update.assert_called_once_with("gc-abc", {"title": "Updated"}, service._session)


class TestDeleteEvent:
    async def test_calls_delete_when_found(self, service):
        service._repo.get_event.return_value = _make_event_orm()

        await service.delete_event(1)

        service._repo.delete_event.assert_called_once_with(1)

    async def test_does_not_call_delete_when_not_found(self, service):
        service._repo.get_event.return_value = None

        await service.delete_event(999)

        service._repo.delete_event.assert_not_called()

    async def test_calls_provider_delete(self, service, mock_provider):
        service._repo.get_event.return_value = _make_event_orm(provider_id="gc-abc")

        await service.delete_event(1)

        mock_provider.delete.assert_called_once_with("gc-abc", service._session)
