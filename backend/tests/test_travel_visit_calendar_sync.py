from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.travel.visits.calendar_sync import VisitCalendarSync, event_description, event_location


def _place(**kw):
    base = dict(name="Cafe Example", city="Lisbon", address=None, maps_url=None, lat=None, lng=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _visit(**kw):
    base = dict(
        id=11, place=_place(), trip_id=1, status="planned", visit_date=date(2026, 12, 18), visit_time=time(20, 0),
        notes="ask for the corner table", calendar_event_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _event(**kw):
    base = dict(
        id=77, recurrence_rule=None, invitees=[], all_day=False, timezone="Europe/Stockholm",
        start_datetime=datetime(2026, 12, 18, 19, 0), end_datetime=datetime(2026, 12, 18, 20, 30),
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def sync():
    svc = VisitCalendarSync(AsyncMock(), AsyncMock())
    svc._events = AsyncMock()
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    svc._stays = AsyncMock()
    svc._stays.get_stays.return_value = []
    svc._trips = AsyncMock()
    svc._trips.get_trip.return_value = SimpleNamespace(default_tag_names="Travel, Work")
    return svc


class TestText:
    def test_location_prefers_the_address_then_name_and_city(self):
        assert event_location(_visit(place=_place(address="Rua Exemplo 1"))) == "Rua Exemplo 1"
        assert event_location(_visit()) == "Cafe Example Lisbon"

    def test_description_has_the_maps_link_and_the_notes(self):
        text = event_description(_visit())
        assert "maps" in text.lower() and "corner table" in text


class TestCreate:
    async def test_builds_the_event_from_the_visit_and_the_trip_tags(self, sync):
        sync._events.create_event.return_value = SimpleNamespace(id=5)
        assert await sync.create_event(_visit()) == 5
        event = sync._events.create_event.await_args.args[0]
        assert event.title == "Cafe Example" and event.tags == ["travel", "work"]
        assert event.start_datetime == datetime(2026, 12, 18, 20, 0)
        assert event.end_datetime - event.start_datetime == timedelta(minutes=90)
        assert event.notification_profile == "normal"

    async def test_duration_comes_from_the_setting(self, sync):
        sync._settings.get_value.return_value = "45"
        sync._events.create_event.return_value = SimpleNamespace(id=5)
        await sync.create_event(_visit())
        event = sync._events.create_event.await_args.args[0]
        assert event.end_datetime - event.start_datetime == timedelta(minutes=45)

    async def test_uses_the_zone_of_the_stay_covering_the_day(self, sync):
        stay = SimpleNamespace(
            timezone="Europe/Stockholm", check_in_at=datetime(2026, 12, 17, 14).astimezone(),
            check_out_at=datetime(2026, 12, 20, 10).astimezone(),
        )
        sync._stays.get_stays.return_value = [stay]
        sync._events.create_event.return_value = SimpleNamespace(id=5)
        await sync.create_event(_visit())
        assert sync._events.create_event.await_args.args[0].timezone == "Europe/Stockholm"

    async def test_needs_a_trip_a_day_and_a_time(self, sync):
        for visit in (_visit(trip_id=None), _visit(visit_date=None), _visit(visit_time=None)):
            assert await sync.create_event(visit) is None
        sync._events.create_event.assert_not_awaited()

    async def test_google_failure_is_logged_not_raised(self, sync, caplog):
        sync._events.create_event.side_effect = RuntimeError("not authorized")
        assert await sync.create_event(_visit()) is None
        assert "Visit event not created" in caplog.text


class TestUpdate:
    async def test_moves_start_end_and_location_keeping_the_duration(self, sync):
        sync._events.get_event.return_value = _event()
        assert await sync.update_event(_visit(calendar_event_id=77, visit_time=time(21, 0))) is True
        update = sync._events.update_event.await_args.args[1]
        assert update.start_datetime == datetime(2026, 12, 18, 21, 0)
        assert update.end_datetime == datetime(2026, 12, 18, 22, 30)
        assert update.model_dump(exclude_unset=True).keys() == {"start_datetime", "end_datetime", "location", "timezone"}

    @pytest.mark.parametrize("override", [{"recurrence_rule": "FREQ=WEEKLY"}, {"invitees": ["a@example.com"]}, {"all_day": True}])
    async def test_recurring_guest_and_all_day_events_are_left_alone(self, sync, override):
        sync._events.get_event.return_value = _event(**override)
        assert await sync.update_event(_visit(calendar_event_id=77)) is False
        sync._events.update_event.assert_not_awaited()

    async def test_a_visit_without_time_leaves_the_event_untouched(self, sync):
        assert await sync.update_event(_visit(calendar_event_id=77, visit_time=None)) is False
        sync._events.get_event.assert_not_awaited()

    async def test_google_failure_is_logged_not_raised(self, sync):
        sync._events.get_event.return_value = _event()
        sync._events.update_event.side_effect = RuntimeError("down")
        assert await sync.update_event(_visit(calendar_event_id=77)) is False


class TestDelete:
    async def test_failure_is_swallowed(self, sync):
        sync._events.delete_event.side_effect = RuntimeError("down")
        assert await sync.delete_event(77) is False


class TestLazyCalendar:
    async def test_the_calendar_service_is_built_once_and_only_when_needed(self):
        events = AsyncMock()
        events.get_event.return_value = None
        factory = AsyncMock(return_value=events)
        svc = VisitCalendarSync(AsyncMock(), factory)
        factory.assert_not_awaited()
        await svc.update_event(_visit(calendar_event_id=1))
        await svc.update_event(_visit(calendar_event_id=2))
        factory.assert_awaited_once()


class TestEventStart:
    async def test_reads_the_start_in_the_events_own_zone(self, sync):
        # Stored starts are naive local time; 19:00 Lisbon in March is 20:00 in Stockholm.
        sync._events.get_event.return_value = _event(start_datetime=datetime(2026, 3, 18, 19, 0), timezone="Europe/Stockholm")
        from unittest.mock import patch
        from zoneinfo import ZoneInfo
        with patch("app.features.travel.visits.calendar_sync.local_timezone", return_value=ZoneInfo("Europe/Lisbon")):
            assert await sync.event_start(77) == (date(2026, 3, 18), time(20, 0))

    async def test_all_day_or_missing_events_have_no_start(self, sync):
        sync._events.get_event.return_value = _event(all_day=True)
        assert await sync.event_start(77) is None
        sync._events.get_event.return_value = None
        assert await sync.event_start(77) is None
