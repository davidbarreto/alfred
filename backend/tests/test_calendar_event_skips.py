from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.assistant.commands.handlers.event import handle_event
from app.features.organizer.calendar_events.repository import CalendarEventRepository
from app.features.organizer.calendar_events.schemas import EventFilters, EventRead, EventUpdate
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.organizer.calendar_events.tables import CalendarEventSkip

AUTH = {"Authorization": "Bearer test-api-token"}
_START = datetime(2026, 11, 4, 14, 30)  # a Wednesday
_END = datetime(2026, 11, 4, 15, 0)


def _orm(skipped: list[date] | None = None, **overrides) -> SimpleNamespace:
    defaults = dict(
        id=1, provider_id="g-1", title="Touchpoint", description=None, location=None, start_datetime=_START,
        end_datetime=_END, all_day=False, host=None, invitees=[], tags=[], recurrence_rule="FREQ=WEEKLY",
        timezone=None, notification_profile=None, availability=None, presence="in_person", travel_minutes=0,
        routine_id=None, skips=[SimpleNamespace(occurrence_date=d) for d in skipped or []],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.fixture
def service():
    svc = CalendarEventService(provider=AsyncMock(), session=AsyncMock())
    svc._repo = AsyncMock()
    svc._repo.get_event.return_value = _orm()
    svc._repo.add_skip.return_value = True
    svc._repo.remove_skip.return_value = True
    return svc


def _range() -> EventFilters:
    return EventFilters(start_from=datetime(2026, 11, 1), start_to=datetime(2026, 11, 30, 23, 59, 59))


class TestGetEventsHidesSkippedOccurrences:
    async def test_skipped_date_is_left_out_of_the_expansion(self, service):
        service._repo.get_events.return_value = [_orm(skipped=[date(2026, 11, 11)])]

        events = await service.get_events(_range())

        assert [e.start_datetime.date().isoformat() for e in events] == [
            "2026-11-04", "2026-11-18", "2026-11-25",
        ]

    async def test_the_series_keeps_its_other_occurrences_and_lists_its_skips(self, service):
        service._repo.get_events.return_value = [_orm(skipped=[date(2026, 11, 11)])]

        events = await service.get_events(_range())

        assert all(e.skips == [date(2026, 11, 11)] for e in events)

    async def test_a_skip_outside_the_range_changes_nothing(self, service):
        service._repo.get_events.return_value = [_orm(skipped=[date(2027, 1, 6)])]

        assert len(await service.get_events(_range())) == 4

    async def test_a_non_recurring_event_is_never_filtered(self, service):
        service._repo.get_events.return_value = [_orm(recurrence_rule=None, skipped=[date(2026, 11, 4)])]

        assert len(await service.get_events(_range())) == 1


class TestSkipOccurrence:
    async def test_skips_a_real_occurrence(self, service):
        result = await service.skip_occurrence(1, date(2026, 11, 11))

        service._repo.add_skip.assert_awaited_once()
        assert service._repo.add_skip.await_args.args[1] == date(2026, 11, 11)
        assert isinstance(result, EventRead)

    async def test_skipping_never_calls_google(self, service):
        await service.skip_occurrence(1, date(2026, 11, 11))

        service._provider.update.assert_not_called()

    async def test_skipping_twice_is_not_an_error(self, service):
        service._repo.add_skip.return_value = False

        assert await service.skip_occurrence(1, date(2026, 11, 11)) is not None

    async def test_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None

        assert await service.skip_occurrence(9, date(2026, 11, 11)) is None

    async def test_event_that_does_not_repeat_is_a_400(self, service):
        service._repo.get_event.return_value = _orm(recurrence_rule=None)

        with pytest.raises(HTTPException) as exc:
            await service.skip_occurrence(1, date(2026, 11, 4))

        assert exc.value.status_code == 400
        service._repo.add_skip.assert_not_called()

    async def test_date_that_is_not_an_occurrence_is_a_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.skip_occurrence(1, date(2026, 11, 12))  # a Thursday

        assert exc.value.status_code == 400
        assert "2026-11-12" in exc.value.detail
        service._repo.add_skip.assert_not_called()


class TestUnskipOccurrence:
    async def test_restores_a_skipped_date(self, service):
        result = await service.unskip_occurrence(1, date(2026, 11, 11))

        assert service._repo.remove_skip.await_args.args[1] == date(2026, 11, 11)
        assert isinstance(result, EventRead)

    async def test_date_that_was_not_skipped_is_a_404(self, service):
        service._repo.remove_skip.return_value = False

        with pytest.raises(HTTPException) as exc:
            await service.unskip_occurrence(1, date(2026, 11, 11))

        assert exc.value.status_code == 404

    async def test_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None

        assert await service.unskip_occurrence(9, date(2026, 11, 11)) is None


class TestEndSeries:
    async def test_sets_an_until_before_the_given_day_through_update(self, service):
        service.update_event = AsyncMock(return_value="updated")

        result = await service.end_series(1, date(2026, 11, 18))

        assert result == "updated"
        event_id, update = service.update_event.await_args.args
        assert event_id == 1
        assert update == EventUpdate(recurrence_rule="FREQ=WEEKLY;UNTIL=20261117T235959Z")

    async def test_all_day_series_gets_a_date_until(self, service):
        service._repo.get_event.return_value = _orm(
            all_day=True, start_datetime=datetime(2026, 11, 4), end_datetime=datetime(2026, 11, 4, 23, 59, 59),
        )
        service.update_event = AsyncMock()

        await service.end_series(1, date(2026, 11, 18))

        assert service.update_event.await_args.args[1].recurrence_rule == "FREQ=WEEKLY;UNTIL=20261117"

    async def test_a_date_at_or_before_the_first_occurrence_is_a_400(self, service):
        with pytest.raises(HTTPException) as exc:
            await service.end_series(1, date(2026, 11, 4))

        assert exc.value.status_code == 400

    async def test_a_series_that_already_ended_cannot_be_extended(self, service):
        service._repo.get_event.return_value = _orm(recurrence_rule="FREQ=WEEKLY;COUNT=3")

        with pytest.raises(HTTPException) as exc:
            await service.end_series(1, date(2027, 1, 6))

        assert exc.value.status_code == 400
        assert "already ends" in exc.value.detail

    async def test_event_that_does_not_repeat_is_a_400(self, service):
        service._repo.get_event.return_value = _orm(recurrence_rule=None)

        with pytest.raises(HTTPException) as exc:
            await service.end_series(1, date(2026, 11, 18))

        assert exc.value.status_code == 400

    async def test_unknown_event_returns_none(self, service):
        service._repo.get_event.return_value = None

        assert await service.end_series(9, date(2026, 11, 18)) is None


class TestRepositorySkips:
    @pytest.fixture
    def repo(self):
        return CalendarEventRepository(AsyncMock())

    async def test_add_skip_appends_and_commits(self, repo):
        event = SimpleNamespace(skips=[])

        assert await repo.add_skip(event, date(2026, 11, 11)) is True

        assert [s.occurrence_date for s in event.skips] == [date(2026, 11, 11)]
        assert isinstance(event.skips[0], CalendarEventSkip)
        repo._session.commit.assert_awaited_once()

    async def test_add_skip_ignores_a_date_already_skipped(self, repo):
        event = SimpleNamespace(skips=[SimpleNamespace(occurrence_date=date(2026, 11, 11))])

        assert await repo.add_skip(event, date(2026, 11, 11)) is False

        assert len(event.skips) == 1
        repo._session.commit.assert_not_called()

    async def test_remove_skip_drops_the_date(self, repo):
        event = SimpleNamespace(skips=[SimpleNamespace(occurrence_date=date(2026, 11, 11))])

        assert await repo.remove_skip(event, date(2026, 11, 11)) is True

        assert event.skips == []
        repo._session.commit.assert_awaited_once()

    async def test_remove_skip_of_an_unknown_date_is_false(self, repo):
        event = SimpleNamespace(skips=[])

        assert await repo.remove_skip(event, date(2026, 11, 11)) is False
        repo._session.commit.assert_not_called()


class TestHandler:
    @pytest.fixture
    def svc(self):
        svc = AsyncMock()
        read = MagicMock()
        read.model_dump.return_value = {"id": 1}
        for name in ("skip_occurrence", "unskip_occurrence", "end_series"):
            getattr(svc, name).return_value = read
        return svc

    async def test_skip_passes_the_event_and_day(self, svc):
        await handle_event("skip", {"id": "1", "date": "2026-11-11"}, svc)

        svc.skip_occurrence.assert_awaited_once_with(1, date(2026, 11, 11))

    async def test_unskip_passes_the_event_and_day(self, svc):
        await handle_event("unskip", {"id": "1", "date": "2026-11-11"}, svc)

        svc.unskip_occurrence.assert_awaited_once_with(1, date(2026, 11, 11))

    async def test_endseries_passes_the_event_and_day(self, svc):
        await handle_event("endseries", {"id": "1", "date": "2026-11-18"}, svc)

        svc.end_series.assert_awaited_once_with(1, date(2026, 11, 18))

    @pytest.mark.parametrize("arguments", [{"id": "1"}, {"id": "1", "date": "next wednesday"}])
    async def test_missing_or_unreadable_date_is_a_400(self, svc, arguments):
        with pytest.raises(HTTPException) as exc:
            await handle_event("skip", arguments, svc)

        assert exc.value.status_code == 400

    async def test_unknown_event_is_a_404(self, svc):
        svc.skip_occurrence.return_value = None

        with pytest.raises(HTTPException) as exc:
            await handle_event("skip", {"id": "9", "date": "2026-11-11"}, svc)

        assert exc.value.status_code == 404


class TestRoutes:
    @pytest.fixture
    def mock_service(self):
        svc = AsyncMock()
        event = EventRead(
            id=1, title="Touchpoint", start_datetime=_START, end_datetime=_END, recurrence_rule="FREQ=WEEKLY",
            skips=[date(2026, 11, 11)],
        )
        svc.skip_occurrence.return_value = event
        svc.unskip_occurrence.return_value = event
        svc.end_series.return_value = event
        return svc

    @pytest.fixture
    def client(self, mock_service):
        from app.dependencies import get_calendar_event_service
        from app.main import app

        app.dependency_overrides[get_calendar_event_service] = lambda: mock_service
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_skip_returns_the_event_with_its_skips(self, client, mock_service):
        resp = client.post("/organizer/calendar-events/1/skips", json={"occurrence_date": "2026-11-11"}, headers=AUTH)

        assert resp.status_code == 200
        assert resp.json()["skips"] == ["2026-11-11"]
        mock_service.skip_occurrence.assert_awaited_once_with(1, date(2026, 11, 11))

    def test_skip_of_an_unknown_event_is_404(self, client, mock_service):
        mock_service.skip_occurrence.return_value = None

        resp = client.post("/organizer/calendar-events/9/skips", json={"occurrence_date": "2026-11-11"}, headers=AUTH)

        assert resp.status_code == 404

    def test_skip_rejects_a_malformed_date(self, client):
        resp = client.post("/organizer/calendar-events/1/skips", json={"occurrence_date": "soon"}, headers=AUTH)

        assert resp.status_code == 422

    def test_unskip_restores_the_date(self, client, mock_service):
        resp = client.delete("/organizer/calendar-events/1/skips/2026-11-11", headers=AUTH)

        assert resp.status_code == 200
        mock_service.unskip_occurrence.assert_awaited_once_with(1, date(2026, 11, 11))

    def test_end_series_passes_the_date(self, client, mock_service):
        resp = client.post("/organizer/calendar-events/1/end-series", json={"from_date": "2026-11-18"}, headers=AUTH)

        assert resp.status_code == 200
        mock_service.end_series.assert_awaited_once_with(1, date(2026, 11, 18))

    def test_end_series_of_an_unknown_event_is_404(self, client, mock_service):
        mock_service.end_series.return_value = None

        resp = client.post("/organizer/calendar-events/9/end-series", json={"from_date": "2026-11-18"}, headers=AUTH)

        assert resp.status_code == 404

    def test_routes_require_auth(self, client):
        assert client.post("/organizer/calendar-events/1/skips", json={"occurrence_date": "2026-11-11"}).status_code == 403
        assert client.post("/organizer/calendar-events/1/end-series", json={"from_date": "2026-11-18"}).status_code == 403
        assert client.delete("/organizer/calendar-events/1/skips/2026-11-11").status_code == 403
