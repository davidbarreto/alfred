from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import CheckConstraint

from app.assistant.commands.handlers.event import handle_event
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.organizer.calendar_events.constants import (
    EVENT_AVAILABILITIES,
    EVENT_PRESENCES,
    effective_availability,
)
from app.features.organizer.calendar_events.schemas import EventCreate, EventRead, EventUpdate
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.calendar_events.tables import CalendarEvent
from app.integrations.google_calendar.provider import GoogleCalendarProvider

_START = datetime(2026, 10, 21, 20, 0)
_END = datetime(2026, 10, 21, 21, 0)


def _orm(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, provider_id="g-1", title="Class", description=None, location=None, start_datetime=_START,
        end_datetime=_END, all_day=False, host=None, invitees=[], tags=[], recurrence_rule=None, timezone=None,
        notification_profile=None, availability=None, presence="in_person", travel_minutes=0, routine_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def provider():
    return AsyncMock()


@pytest.fixture
def service(provider):
    svc = CalendarEventService(provider=provider, session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_event.return_value = _orm()
    svc._repo.update_event.return_value = _orm(availability="blocked", travel_minutes=25)
    return svc


class TestSchemas:
    def test_defaults(self):
        event = EventCreate(title="x", start_datetime=_START, end_datetime=_END)
        assert (event.availability, event.presence, event.travel_minutes, event.routine_id) == (
            None, "in_person", 0, None,
        )

    def test_read_exposes_planning_fields(self):
        read = EventRead.model_validate(_orm(availability="light", presence="remote_home", travel_minutes=25, routine_id=3))
        assert (read.availability, read.presence, read.travel_minutes, read.routine_id) == ("light", "remote_home", 25, 3)

    @pytest.mark.parametrize("field,value", [("availability", "busy"), ("presence", "abroad"), ("travel_minutes", -1)])
    def test_invalid_values_rejected(self, field, value):
        with pytest.raises(ValidationError):
            EventUpdate(**{field: value})

    @pytest.mark.parametrize("field", ["presence", "travel_minutes"])
    def test_required_columns_cannot_be_cleared(self, field):
        with pytest.raises(ValidationError):
            EventUpdate(**{field: None})

    def test_availability_and_routine_can_be_cleared(self):
        update = EventUpdate(availability=None, routine_id=None)
        assert update.model_dump(exclude_unset=True) == {"availability": None, "routine_id": None}

    def test_default_availability(self):
        assert effective_availability(None, all_day=True) == "free"
        assert effective_availability(None, all_day=False) == "blocked"
        assert effective_availability("light", all_day=True) == "light"


class TestTable:
    def test_check_constraints_cover_every_value(self):
        checks = {c.name: str(c.sqltext) for c in CalendarEvent.__table__.constraints if isinstance(c, CheckConstraint)}
        for value in EVENT_AVAILABILITIES:
            assert f"'{value}'" in checks["ck_calendar_events_availability"]
        for value in EVENT_PRESENCES:
            assert f"'{value}'" in checks["ck_calendar_events_presence"]
        assert "ck_calendar_events_travel_minutes" in checks

    def test_routine_foreign_key_sets_null_on_delete(self):
        fk = next(iter(CalendarEvent.__table__.c.routine_id.foreign_keys))
        assert fk.target_fullname == "organizer.routines.id"
        assert fk.ondelete == "SET NULL"


class TestUpdateKeepsPlanningFieldsLocal:
    async def test_update_of_only_planning_fields_makes_no_google_call(self, service, provider):
        result = await service.update_event(1, EventUpdate(availability="blocked", travel_minutes=25))

        provider.update.assert_not_called()
        assert result.travel_minutes == 25
        service._repo.update_event.assert_awaited_once()

    async def test_planning_only_update_works_without_google_authorization(self):
        svc = CalendarEventService(provider=None, session=AsyncMock())
        svc._repo = AsyncMock()
        svc._repo.get_event.return_value = _orm()
        svc._repo.update_event.return_value = _orm(presence="remote_home")

        result = await svc.update_event(1, EventUpdate(presence="remote_home"))

        assert result.presence == "remote_home"

    async def test_planning_only_update_of_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None
        assert await service.update_event(99, EventUpdate(travel_minutes=5)) is None

    async def test_mixed_update_sends_only_google_fields(self, service, provider):
        provider.update.return_value = {
            "start_datetime": _START, "end_datetime": _END, "timezone": "Europe/Lisbon", "id": "g-1",
        }
        await service.update_event(1, EventUpdate(title="Renamed", travel_minutes=25))

        sent = provider.update.call_args.args[1]
        assert sent["title"] == "Renamed"
        persisted = service._repo.update_event.call_args.args[1].model_dump(exclude_unset=True)
        assert persisted["travel_minutes"] == 25

    async def test_empty_update_still_requires_google(self):
        svc = CalendarEventService(provider=None, session=AsyncMock())
        svc._repo = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await svc.update_event(1, EventUpdate())
        assert exc.value.status_code == 503


class TestSyncLeavesPlanningFieldsAlone:
    async def test_sync_update_never_touches_planning_fields(self, provider):
        record = {
            "id": "g-1", "title": "Class", "description": None, "location": None, "start_datetime": _START,
            "end_datetime": _END, "all_day": False, "recurrence_rule": None, "timezone": "Europe/Lisbon",
            "host": None, "invitees": [],
        }
        provider.list.return_value = [record]
        svc = CalendarEventService(provider=provider, session=AsyncMock())
        svc._repo = AsyncMock()
        svc._repo.get_event_by_provider_id.return_value = _orm(id=7, availability="blocked", travel_minutes=25)

        await svc.sync()

        update = svc._repo.update_event.call_args.args[1]
        assert not {"availability", "presence", "travel_minutes", "routine_id"} & set(
            update.model_dump(exclude_unset=True)
        )

    def test_google_payload_has_no_planning_fields(self):
        provider = GoogleCalendarProvider(client=MagicMock(), calendar_id="c", entity_type="calendar_event")
        payload = provider._to_google_event({
            "title": "Class", "start_datetime": _START, "end_datetime": _END,
            "availability": "blocked", "presence": "remote_home", "travel_minutes": 25, "routine_id": 3,
        })
        assert set(payload) == {"summary", "start", "end"}

    def test_events_read_back_from_google_have_no_planning_keys(self):
        provider = GoogleCalendarProvider(client=MagicMock(), calendar_id="c", entity_type="calendar_event")
        record = provider._from_google_event({
            "id": "g", "summary": "x",
            "start": {"dateTime": "2026-10-21T20:00:00+01:00", "timeZone": "Europe/Lisbon"},
            "end": {"dateTime": "2026-10-21T21:00:00+01:00", "timeZone": "Europe/Lisbon"},
        })
        assert not {"availability", "presence", "travel_minutes", "routine_id"} & set(record)


class TestHandler:
    @pytest.fixture
    def mock_service(self):
        svc = AsyncMock()
        svc.create_event.return_value = EventRead.model_validate(_orm())
        svc.update_event.return_value = EventRead.model_validate(_orm())
        return svc

    async def test_add_passes_planning_fields(self, mock_service):
        await handle_event(
            "add",
            {"title": "Capoeira", "start": "2026-10-21T20:00:00", "availability": "Blocked",
             "presence": "in_person", "travel_minutes": "25", "routine_id": "3", "location": "Gym"},
            mock_service,
        )
        payload = mock_service.create_event.call_args.args[0]
        assert (payload.availability, payload.presence, payload.travel_minutes, payload.routine_id) == (
            "blocked", "in_person", 25, 3,
        )
        assert payload.location == "Gym"

    async def test_add_without_planning_fields_keeps_defaults(self, mock_service):
        await handle_event("add", {"title": "Plain", "start": "2026-10-21T20:00:00"}, mock_service)
        payload = mock_service.create_event.call_args.args[0]
        assert (payload.availability, payload.presence, payload.travel_minutes) == (None, "in_person", 0)

    async def test_update_sends_only_given_fields(self, mock_service):
        await handle_event("update", {"id": "4", "travel_minutes": "25"}, mock_service)
        assert mock_service.update_event.call_args.args[1].model_dump(exclude_unset=True) == {"travel_minutes": 25}

    async def test_update_can_clear_availability_and_routine(self, mock_service):
        await handle_event("update", {"id": "4", "availability": "", "routine_id": ""}, mock_service)
        assert mock_service.update_event.call_args.args[1].model_dump(exclude_unset=True) == {
            "availability": None, "routine_id": None,
        }

    @pytest.mark.parametrize("args", [{"availability": "busy"}, {"presence": "abroad"}, {"travel_minutes": "-5"}, {"travel_minutes": "far"}])
    async def test_invalid_values_are_400(self, mock_service, args):
        with pytest.raises(HTTPException) as exc:
            await handle_event("update", {"id": "4", **args}, mock_service)
        assert exc.value.status_code == 400


class TestRegistry:
    def test_update_action_exposes_every_editable_field(self):
        keys = set(COMMAND_DEFINITIONS["event"]["update"]["flags"].values())
        assert {"availability", "presence", "travel_minutes", "routine_id", "title", "start", "end", "tags"} <= keys

    def test_details_name_enum_values_units_and_scope(self):
        for action in ("add", "update"):
            details = COMMAND_DEFINITIONS["event"][action]["details"]
            for value in (*EVENT_AVAILABILITIES, *EVENT_PRESENCES):
                assert value in details
            assert "minutes" in details
            assert "one-way" in details
        assert "whole recurring series" in COMMAND_DEFINITIONS["event"]["update"]["details"]


class TestRecurringOccurrencesInheritPlanningFields:
    async def test_every_occurrence_carries_the_series_planning_fields(self, service):
        weekly = _orm(
            id=7, recurrence_rule="FREQ=WEEKLY;BYDAY=WE", availability="blocked", presence="in_person",
            travel_minutes=25, routine_id=3,
        )
        service._repo.get_events.return_value = [weekly]

        from app.features.organizer.calendar_events.schemas import EventFilters

        occurrences = await service.get_events(
            EventFilters(start_from=datetime(2026, 10, 19), start_to=datetime(2026, 11, 5))
        )

        assert [o.start_datetime.date().isoformat() for o in occurrences] == ["2026-10-21", "2026-10-28", "2026-11-04"]
        for occurrence in occurrences:
            assert (occurrence.availability, occurrence.presence, occurrence.travel_minutes, occurrence.routine_id) == (
                "blocked", "in_person", 25, 3,
            )
