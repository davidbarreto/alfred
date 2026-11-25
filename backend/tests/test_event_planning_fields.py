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
from app.shared.utils.timezone import local_timezone

_START = datetime(2026, 10, 21, 20, 0)
_END = datetime(2026, 10, 21, 21, 0)


_LOCATIONS = {
    5: SimpleNamespace(id=5, name="Office", address="Rua Nova 10\n4000-001 Porto"),
    6: SimpleNamespace(id=6, name="School", address=None),
}
_GOOGLE_RECORD = {"start_datetime": _START, "end_datetime": _END, "timezone": "Europe/Lisbon", "id": "g-1"}


def _orm(**overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, provider_id="g-1", title="Class", description=None, location=None, start_datetime=_START,
        end_datetime=_END, all_day=False, host=None, invitees=[], tags=[], recurrence_rule=None, timezone=None,
        notification_profile=None, availability=None, presence="in_person", travel_minutes=0, routine_id=None,
        place_id=None,
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
    svc._places = AsyncMock()
    svc._places.get_row.side_effect = lambda place_id: _LOCATIONS.get(place_id)
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

    def test_location_foreign_key_sets_null_on_delete(self):
        fk = next(iter(CalendarEvent.__table__.c.place_id.foreign_keys))
        assert fk.target_fullname == "location.places.id"
        assert fk.ondelete == "SET NULL"

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

    async def test_tags_only_update_makes_no_google_call(self, service, provider):
        await service.update_event(1, EventUpdate(tags=["work"]))

        provider.update.assert_not_called()
        service._repo.update_event.assert_awaited_once()

    async def test_tags_only_update_works_without_google_authorization(self):
        svc = CalendarEventService(provider=None, session=AsyncMock())
        svc._repo = AsyncMock()
        svc._repo.get_event.return_value = _orm()
        svc._repo.update_event.return_value = _orm()

        await svc.update_event(1, EventUpdate(tags=["work"]))

        svc._repo.update_event.assert_awaited_once()

    async def test_full_form_post_that_only_changes_tags_makes_no_google_call(self, service, provider):
        # The portal posts every field on each save; unchanged ones must not count as edits.
        await service.update_event(1, EventUpdate(
            title="Class", start_datetime=_START, end_datetime=_END, all_day=False, location=None,
            recurrence_rule=None, timezone=None, notification_profile=None, availability=None,
            presence="in_person", travel_minutes=0, routine_id=None, tags=["work"],
        ))

        provider.update.assert_not_called()
        persisted = service._repo.update_event.call_args.args[1]
        assert persisted.model_dump(exclude_unset=True) == {"tags": ["work"]}

    async def test_unchanged_timezone_aware_datetimes_are_not_edits(self, service, provider):
        aware_start = _START.replace(tzinfo=local_timezone())

        await service.update_event(1, EventUpdate(start_datetime=aware_start, tags=["work"]))

        provider.update.assert_not_called()

    async def test_unchanged_tags_in_a_different_order_are_not_edits(self, service, provider):
        service._repo.get_event.return_value = _orm(tags=[SimpleNamespace(name="a"), SimpleNamespace(name="b")])

        await service.update_event(1, EventUpdate(tags=["b", "a"], travel_minutes=10))

        provider.update.assert_not_called()
        persisted = service._repo.update_event.call_args.args[1]
        assert persisted.model_dump(exclude_unset=True) == {"travel_minutes": 10}

    async def test_changed_title_with_tags_still_goes_to_google(self, service, provider):
        provider.update.return_value = {
            "start_datetime": _START, "end_datetime": _END, "timezone": "Europe/Lisbon", "id": "g-1",
        }

        await service.update_event(1, EventUpdate(title="Renamed", start_datetime=_START, tags=["work"]))

        provider.update.assert_awaited_once()

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


class TestLocation:
    async def test_linking_keeps_text_the_user_typed_and_skips_google(self, service, provider):
        service._repo.get_event.return_value = _orm(location="Meeting room 3")
        service._repo.update_event.return_value = _orm(place_id=5, location="Meeting room 3")
        result = await service.update_event(1, EventUpdate(place_id=5))
        provider.update.assert_not_called()
        assert result.place_id == 5
        assert service._repo.update_event.call_args.args[1].model_dump(exclude_unset=True) == {"place_id": 5}

    async def test_linking_without_google_still_works_and_fills_nothing(self):
        svc = CalendarEventService(provider=None, session=AsyncMock())
        svc._repo = AsyncMock()
        svc._repo.get_event.return_value = _orm()
        svc._repo.update_event.return_value = _orm(place_id=5)
        svc._places = AsyncMock()
        svc._places.get_row.side_effect = lambda place_id: _LOCATIONS.get(place_id)
        await svc.update_event(1, EventUpdate(place_id=5))
        assert svc._repo.update_event.call_args.args[1].model_dump(exclude_unset=True) == {"place_id": 5}

    async def test_location_can_be_cleared(self, service, provider):
        service._repo.get_event.return_value = _orm(place_id=5, location="Rua Nova 10, 4000-001 Porto")
        await service.update_event(1, EventUpdate(place_id=None))
        provider.update.assert_not_called()
        assert service._repo.update_event.call_args.args[1].model_dump(exclude_unset=True) == {"place_id": None}

    async def test_google_never_receives_the_location_id(self, service, provider):
        provider.update.return_value = _GOOGLE_RECORD
        provider.create.return_value = _GOOGLE_RECORD
        service._repo.create_event.return_value = _orm(place_id=5)

        await service.update_event(1, EventUpdate(title="Renamed", place_id=5, travel_minutes=10))
        await service.create_event(EventCreate(title="x", start_datetime=_START, end_datetime=_END, place_id=5))

        assert set(provider.update.call_args.args[1]) == {"title", "location"}
        sent = provider.create.call_args.args[0]
        assert not {"place_id", "travel_minutes", "availability", "presence", "routine_id", "tags"} & set(sent)
        assert service._repo.create_event.call_args.args[0].place_id == 5

    async def test_unknown_location_is_422(self, service, provider):
        service._places.get_row.side_effect = lambda place_id: None
        with pytest.raises(HTTPException) as exc:
            await service.update_event(1, EventUpdate(place_id=99))
        assert exc.value.status_code == 422
        with pytest.raises(HTTPException):
            await service.create_event(EventCreate(title="x", start_datetime=_START, end_datetime=_END, place_id=99))
        provider.create.assert_not_called()

    async def test_find_place_id_goes_through_the_everyday_lookup(self, service, monkeypatch):
        everyday = AsyncMock()
        everyday.find.side_effect = lambda ref: SimpleNamespace(id=6, name="School") if "school" in ref else None
        monkeypatch.setattr(
            "app.features.organizer.calendar_events.service.EverydayPlaceService", lambda session, places: everyday
        )
        assert await service.find_place_id(" school ") == 6
        with pytest.raises(HTTPException) as exc:
            await service.find_place_id("Nowhere")
        assert exc.value.status_code == 422

    async def test_every_occurrence_of_a_series_is_at_its_location(self, service):
        service._repo.get_events.return_value = [_orm(id=7, recurrence_rule="FREQ=WEEKLY;BYDAY=WE", place_id=5)]
        from app.features.organizer.calendar_events.schemas import EventFilters

        occurrences = await service.get_events(
            EventFilters(start_from=datetime(2026, 10, 19), start_to=datetime(2026, 11, 5), place_id=5)
        )

        assert len(occurrences) == 3 and {o.place_id for o in occurrences} == {5}
        assert service._repo.get_events.call_args.args[0].place_id == 5


class TestCalendarTextFollowsTheLocation:
    async def test_create_fills_the_address_on_one_line(self, service, provider):
        provider.create.return_value = _GOOGLE_RECORD
        service._repo.create_event.return_value = _orm(place_id=5)

        await service.create_event(EventCreate(title="Office", start_datetime=_START, end_datetime=_END, place_id=5))

        assert provider.create.call_args.args[0]["location"] == "Rua Nova 10, 4000-001 Porto"
        assert service._repo.create_event.call_args.args[0].location == "Rua Nova 10, 4000-001 Porto"

    async def test_create_uses_the_name_without_an_address(self, service, provider):
        provider.create.return_value = _GOOGLE_RECORD
        service._repo.create_event.return_value = _orm(place_id=6)
        await service.create_event(EventCreate(title="Pickup", start_datetime=_START, end_datetime=_END, place_id=6))
        assert provider.create.call_args.args[0]["location"] == "School"

    @pytest.mark.parametrize("extra", [{"location": "Gate B"}, {"invitees": ["someone@example.com"]}])
    async def test_create_keeps_typed_text_and_meetings_with_invitees(self, service, provider, extra):
        provider.create.return_value = _GOOGLE_RECORD
        service._repo.create_event.return_value = _orm(place_id=5)
        await service.create_event(
            EventCreate(title="x", start_datetime=_START, end_datetime=_END, place_id=5, **extra)
        )
        assert provider.create.call_args.args[0].get("location") == extra.get("location")

    async def test_linking_an_event_with_no_text_writes_it_to_google(self, service, provider):
        provider.update.return_value = _GOOGLE_RECORD

        await service.update_event(1, EventUpdate(place_id=6))

        assert provider.update.call_args.args[1] == {"location": "School"}
        persisted = service._repo.update_event.call_args.args[1].model_dump(exclude_unset=True)
        assert persisted["place_id"] == 6 and persisted["location"] == "School"

    async def test_relinking_replaces_the_previous_locations_text(self, service, provider):
        provider.update.return_value = _GOOGLE_RECORD
        service._repo.get_event.return_value = _orm(place_id=5, location="rua nova 10,  4000-001 porto")

        await service.update_event(1, EventUpdate(place_id=6))

        assert provider.update.call_args.args[1] == {"location": "School"}

    async def test_full_form_post_that_only_relinks_fills_the_text(self, service, provider):
        """The portal posts the unchanged old text with the new link: the text still follows the location."""
        provider.update.return_value = _GOOGLE_RECORD
        service._repo.get_event.return_value = _orm(place_id=6, location="School")

        await service.update_event(1, EventUpdate(title="Class", location="School", place_id=5))

        assert provider.update.call_args.args[1]["location"] == "Rua Nova 10, 4000-001 Porto"

    async def test_text_edited_in_the_same_update_wins(self, service, provider):
        provider.update.return_value = _GOOGLE_RECORD
        await service.update_event(1, EventUpdate(location="Back entrance", place_id=5))
        assert provider.update.call_args.args[1] == {"location": "Back entrance"}

    async def test_events_with_invitees_keep_their_text(self, service, provider):
        service._repo.get_event.return_value = _orm(invitees=[SimpleNamespace(email="someone@example.com")])
        await service.update_event(1, EventUpdate(place_id=5))
        provider.update.assert_not_called()


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
        assert not {"availability", "presence", "travel_minutes", "routine_id", "place_id"} & set(
            update.model_dump(exclude_unset=True)
        )

    def test_google_payload_has_no_planning_fields(self):
        provider = GoogleCalendarProvider(client=MagicMock(), calendar_id="c", entity_type="calendar_event")
        payload = provider._to_google_event({
            "title": "Class", "start_datetime": _START, "end_datetime": _END,
            "availability": "blocked", "presence": "remote_home", "travel_minutes": 25, "routine_id": 3,
            "tags": ["work"],
        })
        assert set(payload) == {"summary", "start", "end"}

    def test_events_read_back_from_google_have_no_planning_keys(self):
        provider = GoogleCalendarProvider(client=MagicMock(), calendar_id="c", entity_type="calendar_event")
        record = provider._from_google_event({
            "id": "g", "summary": "x",
            "start": {"dateTime": "2026-10-21T20:00:00+01:00", "timeZone": "Europe/Lisbon"},
            "end": {"dateTime": "2026-10-21T21:00:00+01:00", "timeZone": "Europe/Lisbon"},
        })
        assert not {"availability", "presence", "travel_minutes", "routine_id", "tags"} & set(record)


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
            {"title": "Evening class", "start": "2026-10-21T20:00:00", "availability": "Blocked",
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

    async def test_at_takes_a_location_name_or_id_and_empty_clears(self, mock_service):
        mock_service.find_place_id.return_value = 5
        await handle_event("add", {"title": "Pickup", "start": "2026-10-21T17:00:00", "place_id": "School"},
                           mock_service)
        mock_service.find_place_id.assert_awaited_with("School")
        assert mock_service.create_event.call_args.args[0].place_id == 5

        await handle_event("update", {"id": "4", "place_id": ""}, mock_service)
        assert mock_service.update_event.call_args.args[1].model_dump(exclude_unset=True) == {"place_id": None}

    @pytest.mark.parametrize("args", [{"availability": "busy"}, {"presence": "abroad"}, {"travel_minutes": "-5"}, {"travel_minutes": "far"}])
    async def test_invalid_values_are_400(self, mock_service, args):
        with pytest.raises(HTTPException) as exc:
            await handle_event("update", {"id": "4", **args}, mock_service)
        assert exc.value.status_code == 400


class TestRegistry:
    def test_update_action_exposes_every_editable_field(self):
        keys = set(COMMAND_DEFINITIONS["event"]["update"]["flags"].values())
        assert {
            "availability", "presence", "travel_minutes", "routine_id", "place_id", "title", "start", "end", "tags",
        } <= keys
        assert COMMAND_DEFINITIONS["event"]["add"]["flags"]["--at"] == "place_id"

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
