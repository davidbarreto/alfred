from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import CheckConstraint, UniqueConstraint

from app.assistant.commands.handlers.event import handle_event
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.organizer.calendar_events.recurrence import occurrence_instance_id
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventFilters, EventRead, EventRescheduleRequest
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.calendar_events.tables import CalendarEventOverride
from app.integrations.google_calendar.provider import GoogleCalendarProvider

AUTH = {"Authorization": "Bearer test-api-token"}
_START = datetime(2026, 11, 2, 14, 30)  # a Monday; Lisbon is UTC+0 in November
_END = datetime(2026, 11, 2, 15, 0)
_FRIDAY = date(2026, 11, 6)


def _orm(skipped=None, moved=None, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, provider_id="g-1", title="Pickup", description=None, location=None, start_datetime=_START,
        end_datetime=_END, all_day=False, host=None, invitees=[], tags=[], recurrence_rule="FREQ=WEEKLY;BYDAY=MO,WE,FR",
        timezone=None, notification_profile=None, availability=None, presence="in_person", travel_minutes=0,
        routine_id=None, skips=[SimpleNamespace(occurrence_date=d) for d in skipped or []],
        overrides=[SimpleNamespace(occurrence_date=d, start_datetime=s, end_datetime=e) for d, s, e in moved or []],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def service():
    svc = CalendarEventService(provider=AsyncMock(), session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_event.return_value = _orm()
    svc._provider.update.side_effect = lambda record_id, record, session: {
        "start_datetime": record["start_datetime"], "end_datetime": record["end_datetime"],
    }
    return svc


def _week() -> EventFilters:
    return EventFilters(start_from=datetime(2026, 11, 2), start_to=datetime(2026, 11, 8, 23, 59, 59))


class TestInstanceId:
    def test_is_the_series_id_plus_the_original_start_in_utc(self):
        assert occurrence_instance_id("abc", datetime(2026, 11, 6, 15, 20)) == "abc_20261106T152000Z"

    def test_local_summer_time_is_converted_to_utc(self):
        assert occurrence_instance_id("abc", datetime(2026, 7, 6, 15, 20)) == "abc_20260706T142000Z"


class TestGetEventsListsMovedOccurrences:
    async def test_a_moved_occurrence_shows_at_its_new_time_and_the_others_stay(self, service):
        new_start, new_end = datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30)
        service._repo.get_events.return_value = [_orm(moved=[(_FRIDAY, new_start, new_end)])]

        events = await service.get_events(_week())

        assert [e.start_datetime for e in events] == [
            datetime(2026, 11, 2, 14, 30), datetime(2026, 11, 4, 14, 30), new_start,
        ]
        assert events[-1].end_datetime == new_end

    async def test_moving_to_another_day_removes_it_from_the_original_day(self, service):
        moved_to = datetime(2026, 11, 10, 9, 0)
        service._repo.get_events.return_value = [_orm(moved=[(_FRIDAY, moved_to, datetime(2026, 11, 10, 9, 30))])]

        events = await service.get_events(_week())

        assert [e.start_datetime.date().isoformat() for e in events] == ["2026-11-02", "2026-11-04"]

    async def test_an_occurrence_moved_into_the_range_from_outside_it_is_listed(self, service):
        original = date(2026, 11, 13)
        service._repo.get_events.return_value = [
            _orm(moved=[(original, datetime(2026, 11, 7, 10, 0), datetime(2026, 11, 7, 10, 30))])
        ]

        events = await service.get_events(_week())

        assert datetime(2026, 11, 7, 10, 0) in [e.start_datetime for e in events]

    async def test_an_occurrence_moved_out_of_the_range_is_not_listed(self, service):
        service._repo.get_events.return_value = [
            _orm(moved=[(_FRIDAY, datetime(2026, 11, 20, 10, 0), datetime(2026, 11, 20, 10, 30))])
        ]

        events = await service.get_events(_week())

        assert all(e.start_datetime.date() != _FRIDAY for e in events) and len(events) == 2

    async def test_a_skipped_moved_occurrence_stays_hidden(self, service):
        service._repo.get_events.return_value = [
            _orm(skipped=[_FRIDAY], moved=[(_FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))])
        ]

        assert len(await service.get_events(_week())) == 2

    async def test_the_series_lists_its_overrides(self, service):
        moved = [(_FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))]
        service._repo.get_events.return_value = [_orm(moved=moved)]

        events = await service.get_events(_week())

        assert events[0].overrides[0].occurrence_date == _FRIDAY

    async def test_overrides_serialise_with_a_utc_offset(self, service):
        read = EventRead.model_validate(_orm(moved=[(_FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))]))
        assert read.model_dump(mode="json")["overrides"][0]["start_datetime"] == "2026-11-06T16:00:00+00:00"


class TestRescheduleOccurrence:
    async def test_writes_the_instance_through_to_google_then_stores_the_override(self, service):
        start, end = datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30)

        result = await service.reschedule_occurrence(1, _FRIDAY, start, end)

        record_id, record, _ = service._provider.update.await_args.args
        assert record_id == "g-1_20261106T143000Z"
        assert record == {"start_datetime": start, "end_datetime": end}
        service._repo.set_override.assert_awaited_once()
        assert service._repo.set_override.await_args.args[1:] == (_FRIDAY, start, end)
        assert isinstance(result, EventRead)

    async def test_the_stored_times_are_the_ones_google_answers_with(self, service):
        service._provider.update.side_effect = None
        service._provider.update.return_value = {
            "start_datetime": datetime(2026, 11, 6, 16, 1), "end_datetime": datetime(2026, 11, 6, 16, 31),
        }

        await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))

        assert service._repo.set_override.await_args.args[2] == datetime(2026, 11, 6, 16, 1)

    async def test_without_an_end_the_occurrence_keeps_its_length(self, service):
        await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0))

        assert service._provider.update.await_args.args[1]["end_datetime"] == datetime(2026, 11, 6, 16, 30)

    async def test_can_move_to_another_day(self, service):
        await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 7, 10, 0), datetime(2026, 11, 7, 10, 30))
        service._repo.set_override.assert_awaited_once()

    @pytest.mark.parametrize("change,status_code", [
        ({"recurrence_rule": None}, 400), ({"all_day": True}, 400), ({"skipped": [_FRIDAY]}, 409),
    ])
    async def test_refuses_what_cannot_be_moved(self, service, change, status_code):
        service._repo.get_event.return_value = _orm(**change)

        with pytest.raises(HTTPException) as exc:
            await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))

        assert exc.value.status_code == status_code
        service._provider.update.assert_not_called()
        service._repo.set_override.assert_not_called()

    async def test_a_date_that_is_not_an_occurrence_is_a_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.reschedule_occurrence(1, date(2026, 11, 5), datetime(2026, 11, 5, 9, 0), datetime(2026, 11, 5, 10, 0))
        assert exc.value.status_code == 400 and "2026-11-05" in exc.value.detail

    async def test_the_end_must_follow_the_start(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 15, 0))
        assert exc.value.status_code == 400

    async def test_needs_google_authorisation(self):
        svc = CalendarEventService(provider=None, session=AsyncMock())
        svc._repo = AsyncMock()
        svc._repo.get_event.return_value = _orm()

        with pytest.raises(HTTPException) as exc:
            await svc.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))

        assert exc.value.status_code == 503
        svc._repo.set_override.assert_not_called()

    async def test_a_google_failure_stores_nothing(self, service):
        service._provider.update.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await service.reschedule_occurrence(1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))

        service._repo.set_override.assert_not_called()

    async def test_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None
        assert await service.reschedule_occurrence(9, _FRIDAY, datetime(2026, 11, 6, 16, 0)) is None


class TestRestoreOccurrence:
    @pytest.fixture
    def moved(self, service):
        service._repo.get_event.return_value = _orm(moved=[(_FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))])

    async def test_writes_the_original_time_back_to_google_and_forgets_the_override(self, service, moved):
        await service.restore_occurrence(1, _FRIDAY)

        record_id, record, _ = service._provider.update.await_args.args
        assert record_id == "g-1_20261106T143000Z"
        assert record == {"start_datetime": datetime(2026, 11, 6, 14, 30), "end_datetime": datetime(2026, 11, 6, 15, 0)}
        assert service._repo.remove_override.await_args.args[1] == _FRIDAY

    async def test_a_date_that_was_not_moved_is_a_404(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.restore_occurrence(1, _FRIDAY)
        assert exc.value.status_code == 404
        service._provider.update.assert_not_called()

    async def test_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None
        assert await service.restore_occurrence(9, _FRIDAY) is None


class TestEndSeriesForgetsLaterOverrides:
    async def test_removal_runs_after_the_series_was_updated(self, service):
        event = _orm(
            start_datetime=datetime(2026, 10, 28, 14, 30), end_datetime=datetime(2026, 10, 28, 15, 0),
            moved=[(_FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))],
        )
        service._repo.get_event.return_value = event
        order = []
        service.update_event = AsyncMock(side_effect=lambda *a: order.append("update") or SimpleNamespace())
        service._repo.remove_overrides_from.side_effect = lambda *a: order.append("remove")
        service.get_event = AsyncMock(return_value="fresh")

        result = await service.end_series(1, date(2026, 11, 5))

        assert order == ["update", "remove"]
        assert service._repo.remove_overrides_from.await_args.args[1] == date(2026, 11, 5)
        assert result == "fresh"

    async def test_overrides_before_the_new_end_are_kept(self, service):
        event = _orm(
            start_datetime=datetime(2026, 10, 28, 14, 30), end_datetime=datetime(2026, 10, 28, 15, 0),
            moved=[(date(2026, 11, 2), datetime(2026, 11, 2, 16, 0), datetime(2026, 11, 2, 16, 30))],
        )
        service._repo.get_event.return_value = event
        service.update_event = AsyncMock(return_value="updated")

        assert await service.end_series(1, date(2026, 11, 5)) == "updated"
        service._repo.remove_overrides_from.assert_not_called()


class TestSyncTurnsGoogleExceptionsIntoOverrides:
    @pytest.fixture
    def sync_service(self, service):
        service._repo.get_event_by_provider_id = AsyncMock()
        return service

    def _exception(self, **extra):
        return {
            "id": "g-1_20261106T143000Z", "title": "Pickup", "description": None, "location": None,
            "start_datetime": datetime(2026, 11, 6, 16, 0), "end_datetime": datetime(2026, 11, 6, 16, 30),
            "all_day": False, "recurrence_rule": None, "timezone": "Europe/Lisbon", "host": None, "invitees": [],
            "recurring_event_id": "g-1", "original_start": datetime(2026, 11, 6, 14, 30), **extra,
        }

    async def test_a_moved_instance_becomes_an_override_of_its_series_not_a_new_event(self, sync_service):
        series = _orm()
        sync_service._provider.list.return_value = [self._exception()]
        sync_service._repo.get_event_by_provider_id.side_effect = lambda pid: series if pid == "g-1" else None

        result = await sync_service.sync(date(2026, 11, 1), date(2026, 11, 30))

        sync_service._repo.set_override.assert_awaited_once_with(
            series, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30)
        )
        sync_service._repo.create_event.assert_not_called()
        sync_service._repo.update_event.assert_not_called()
        assert (result.created, result.updated) == (0, 1)

    async def test_a_standalone_copy_imported_by_an_earlier_sync_is_deleted(self, sync_service):
        series, duplicate = _orm(), SimpleNamespace(id=77)
        sync_service._provider.list.return_value = [self._exception()]
        sync_service._repo.get_event_by_provider_id.side_effect = lambda pid: series if pid == "g-1" else duplicate

        await sync_service.sync(date(2026, 11, 1), date(2026, 11, 30))

        sync_service._repo.delete_event.assert_awaited_once_with(77)

    async def test_an_instance_of_an_unknown_series_is_ignored(self, sync_service):
        sync_service._provider.list.return_value = [self._exception()]
        sync_service._repo.get_event_by_provider_id.return_value = None

        result = await sync_service.sync(date(2026, 11, 1), date(2026, 11, 30))

        sync_service._repo.set_override.assert_not_called()
        sync_service._repo.create_event.assert_not_called()
        assert (result.created, result.updated) == (0, 0)


class TestGoogleProviderExceptions:
    def _provider(self):
        return GoogleCalendarProvider(client=AsyncMock(), calendar_id="primary")

    def test_an_exception_instance_carries_its_series_and_original_start_in_local_time(self):
        record = self._provider()._from_google_event({
            "id": "g-1_20260706T142000Z", "summary": "Pickup", "recurringEventId": "g-1",
            "originalStartTime": {"dateTime": "2026-07-06T14:20:00Z"},
            "start": {"dateTime": "2026-07-06T16:00:00+01:00"}, "end": {"dateTime": "2026-07-06T16:30:00+01:00"},
        })

        assert record["recurring_event_id"] == "g-1"
        assert record["original_start"] == datetime(2026, 7, 6, 15, 20)  # Lisbon summer time
        assert record["start_datetime"] == datetime(2026, 7, 6, 16, 0)

    def test_an_all_day_original_start_is_a_date(self):
        record = self._provider()._from_google_event({
            "id": "g-1_20260706", "summary": "Day", "recurringEventId": "g-1", "originalStartTime": {"date": "2026-07-06"},
            "start": {"date": "2026-07-07"}, "end": {"date": "2026-07-08"},
        })
        assert record["original_start"] == datetime(2026, 7, 6)

    def test_a_plain_event_has_neither_key(self):
        record = self._provider()._from_google_event({
            "id": "g-2", "summary": "Plain",
            "start": {"dateTime": "2026-07-06T14:20:00Z"}, "end": {"dateTime": "2026-07-06T15:20:00Z"},
        })
        assert "recurring_event_id" not in record and "original_start" not in record


class TestRepositoryOverrides:
    @pytest.fixture
    def repo(self):
        return CalendarEventRepository(AsyncMock())

    async def test_set_override_appends_a_new_one_and_commits(self, repo):
        event = SimpleNamespace(overrides=[])

        await repo.set_override(event, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30))

        assert isinstance(event.overrides[0], CalendarEventOverride)
        assert event.overrides[0].occurrence_date == _FRIDAY
        repo._session.commit.assert_awaited_once()

    async def test_set_override_updates_an_existing_one_in_place(self, repo):
        existing = SimpleNamespace(occurrence_date=_FRIDAY, start_datetime=None, end_datetime=None)
        event = SimpleNamespace(overrides=[existing])

        await repo.set_override(event, _FRIDAY, datetime(2026, 11, 6, 17, 0), datetime(2026, 11, 6, 17, 30))

        assert event.overrides == [existing] and existing.start_datetime == datetime(2026, 11, 6, 17, 0)
        assert existing.end_datetime == datetime(2026, 11, 6, 17, 30)

    async def test_remove_override(self, repo):
        event = SimpleNamespace(overrides=[SimpleNamespace(occurrence_date=_FRIDAY)])
        assert await repo.remove_override(event, _FRIDAY) is True
        assert event.overrides == []
        repo._session.commit.assert_awaited_once()

    async def test_remove_override_of_an_unmoved_date_is_false(self, repo):
        assert await repo.remove_override(SimpleNamespace(overrides=[]), _FRIDAY) is False
        repo._session.commit.assert_not_called()

    async def test_remove_overrides_from_keeps_earlier_ones(self, repo):
        early, late = SimpleNamespace(occurrence_date=date(2026, 11, 2)), SimpleNamespace(occurrence_date=_FRIDAY)
        event = SimpleNamespace(overrides=[early, late])

        await repo.remove_overrides_from(event, date(2026, 11, 5))

        assert event.overrides == [early]
        repo._session.commit.assert_awaited_once()

    async def test_remove_overrides_from_with_nothing_to_remove_does_not_commit(self, repo):
        await repo.remove_overrides_from(SimpleNamespace(overrides=[]), date(2026, 11, 5))
        repo._session.commit.assert_not_called()


class TestTable:
    def test_one_override_per_event_and_date_and_the_span_is_ordered(self):
        args = CalendarEventOverride.__table_args__
        assert any(isinstance(a, UniqueConstraint) and a.name == "uq_calendar_event_overrides_event_date" for a in args)
        assert any(isinstance(a, CheckConstraint) and a.name == "ck_calendar_event_overrides_order" for a in args)

    def test_new_entity_declares_both_timestamps(self):
        columns = CalendarEventOverride.__table__.columns
        assert "created_at" in columns and "updated_at" in columns


class TestRequestSchema:
    def test_aware_datetimes_become_naive_local_time(self):
        request = EventRescheduleRequest(
            occurrence_date="2026-07-06", start_datetime="2026-07-06T15:00:00+00:00", end_datetime="2026-07-06T15:30:00+00:00",
        )
        assert request.start_datetime == datetime(2026, 7, 6, 16, 0)  # Lisbon summer time

    def test_end_must_follow_start(self):
        with pytest.raises(ValidationError):
            EventRescheduleRequest(
                occurrence_date="2026-11-06", start_datetime="2026-11-06T16:00:00", end_datetime="2026-11-06T16:00:00",
            )


class TestHandler:
    @pytest.fixture
    def svc(self):
        svc = AsyncMock()
        read = MagicMock()
        read.model_dump.return_value = {"id": 1}
        svc.reschedule_occurrence.return_value = read
        svc.restore_occurrence.return_value = read
        return svc

    async def test_a_bare_clock_time_means_that_time_on_the_occurrence_day(self, svc):
        await handle_event("reschedule", {"id": "1", "date": "2026-11-06", "start": "16:00", "end": "16:30"}, svc)

        svc.reschedule_occurrence.assert_awaited_once_with(
            1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30)
        )

    async def test_end_is_optional(self, svc):
        await handle_event("reschedule", {"id": "1", "date": "2026-11-06", "start": "16:00"}, svc)
        assert svc.reschedule_occurrence.await_args.args[3] is None

    async def test_an_iso_datetime_can_move_it_to_another_day(self, svc):
        await handle_event("reschedule", {"id": "1", "date": "2026-11-06", "start": "2026-11-07T10:00:00", "end": "11:00"}, svc)
        assert svc.reschedule_occurrence.await_args.args[2:] == (datetime(2026, 11, 7, 10, 0), datetime(2026, 11, 7, 11, 0))

    @pytest.mark.parametrize("arguments", [
        {"id": "1", "date": "2026-11-06"}, {"id": "1", "date": "2026-11-06", "start": "25:00"},
        {"id": "1", "start": "16:00"},
    ])
    async def test_missing_or_unreadable_arguments_are_400(self, svc, arguments):
        with pytest.raises(HTTPException) as exc:
            await handle_event("reschedule", arguments, svc)
        assert exc.value.status_code == 400
        svc.reschedule_occurrence.assert_not_called()

    async def test_unreschedule_passes_the_event_and_day(self, svc):
        await handle_event("unreschedule", {"id": "1", "date": "2026-11-06"}, svc)
        svc.restore_occurrence.assert_awaited_once_with(1, _FRIDAY)

    @pytest.mark.parametrize("command", ["reschedule", "unreschedule"])
    async def test_unknown_event_is_a_404(self, svc, command):
        svc.reschedule_occurrence.return_value = None
        svc.restore_occurrence.return_value = None
        with pytest.raises(HTTPException) as exc:
            await handle_event(command, {"id": "9", "date": "2026-11-06", "start": "16:00"}, svc)
        assert exc.value.status_code == 404

    def test_commands_are_registered_without_clashing_with_the_move_alias(self):
        events = COMMAND_DEFINITIONS["event"]
        assert {"reschedule", "unreschedule"} <= set(events)
        assert "/move" in events["update"]["aliases"] and "/move" not in events["reschedule"]["aliases"]


class TestRoutes:
    @pytest.fixture
    def mock_service(self):
        svc = AsyncMock()
        event = EventRead(id=1, title="Pickup", start_datetime=_START, end_datetime=_END, recurrence_rule="FREQ=WEEKLY")
        svc.reschedule_occurrence.return_value = event
        svc.restore_occurrence.return_value = event
        return svc

    @pytest.fixture
    def client(self, mock_service):
        from app.dependencies import get_calendar_event_service
        from app.main import app

        app.dependency_overrides[get_calendar_event_service] = lambda: mock_service
        yield TestClient(app)
        app.dependency_overrides.clear()

    _BODY = {"occurrence_date": "2026-11-06", "start_datetime": "2026-11-06T16:00:00", "end_datetime": "2026-11-06T16:30:00"}

    def test_reschedule_passes_the_date_and_new_span(self, client, mock_service):
        resp = client.post("/organizer/calendar-events/1/overrides", json=self._BODY, headers=AUTH)

        assert resp.status_code == 200
        mock_service.reschedule_occurrence.assert_awaited_once_with(
            1, _FRIDAY, datetime(2026, 11, 6, 16, 0), datetime(2026, 11, 6, 16, 30)
        )

    def test_reschedule_of_an_unknown_event_is_404(self, client, mock_service):
        mock_service.reschedule_occurrence.return_value = None
        assert client.post("/organizer/calendar-events/9/overrides", json=self._BODY, headers=AUTH).status_code == 404

    @pytest.mark.parametrize("body", [
        {"occurrence_date": "soon", "start_datetime": "2026-11-06T16:00:00", "end_datetime": "2026-11-06T16:30:00"},
        {"occurrence_date": "2026-11-06", "start_datetime": "2026-11-06T16:00:00", "end_datetime": "2026-11-06T15:00:00"},
        {"occurrence_date": "2026-11-06", "start_datetime": "2026-11-06T16:00:00"},
    ])
    def test_reschedule_validates_the_body(self, client, body):
        assert client.post("/organizer/calendar-events/1/overrides", json=body, headers=AUTH).status_code == 422

    def test_restore_passes_the_date(self, client, mock_service):
        resp = client.delete("/organizer/calendar-events/1/overrides/2026-11-06", headers=AUTH)

        assert resp.status_code == 200
        mock_service.restore_occurrence.assert_awaited_once_with(1, _FRIDAY)

    def test_restore_of_an_unknown_event_is_404(self, client, mock_service):
        mock_service.restore_occurrence.return_value = None
        assert client.delete("/organizer/calendar-events/9/overrides/2026-11-06", headers=AUTH).status_code == 404

    def test_routes_require_auth(self, client):
        assert client.post("/organizer/calendar-events/1/overrides", json=self._BODY).status_code == 403
        assert client.delete("/organizer/calendar-events/1/overrides/2026-11-06").status_code == 403
