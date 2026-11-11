from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.core.reminders.service import ReminderService
from app.features.travel.legs.schemas import LegRead
from app.features.travel.places.schemas import PlaceRead
from app.features.travel.reminders import (
    TravelReminder,
    TravelReminderService,
    build_travel_reminders,
)
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate
from app.features.travel.settings_service import (
    DEFAULT_AIRPORT_BUFFER_MIN,
    DEFAULT_HOME_TO_AIRPORT_MIN,
    TravelSettingsService,
)
from app.features.travel.stays.schemas import StayRead
from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.timeline import build_timeline, leave_home_at

CREATED = datetime(2026, 1, 1, tzinfo=timezone.utc)
SETTINGS = TravelSettingsRead(airport_buffer_min=120, home_to_airport_min=60)


def _utc(day, hour, minute=0):
    return datetime(2026, 12, day, hour, minute, tzinfo=timezone.utc)


def _leg(id=1, departs=None, arrives=None, mode="flight", **kw):
    departs = departs or _utc(17, 12)
    base = dict(
        id=id, trip_id=1, mode=mode, origin="Alpha", destination="Beta", origin_code=None, destination_code=None,
        departs_at=departs, arrives_at=arrives or departs + timedelta(hours=3), departs_tz="UTC", arrives_tz="UTC",
        carrier="XX", number="123", booking_ref=None, booking_url=None, seat=None, notes=None,
        created_at=CREATED, updated_at=CREATED,
    )
    base.update(kw)
    return LegRead(**base)


def _stay(id=1, check_in=None, check_out=None):
    place = PlaceRead(
        id=1, kind="hotel", name="Hotel Example", city="Beta", country=None, maps_url=None, lat=None, lng=None,
        address=None, notes=None, created_at=CREATED, updated_at=CREATED,
    )
    return StayRead(
        id=id, trip_id=1, place_id=1, place=place, check_in_at=check_in or _utc(17, 15), check_out_at=check_out or _utc(19, 10),
        timezone="UTC", booking_ref=None, booking_url=None, notes=None, grade=None, created_at=CREATED, updated_at=CREATED,
    )


def _trip(legs=(), stays=(), start=date(2026, 12, 17), checklist_note_id=None):
    return TripDetail(
        id=1, name="Example trip", start_date=start, end_date=date(2026, 12, 24), travelers=None, preferences=None,
        checklist_note_id=checklist_note_id, notes=None, default_tag_names=None, tags=[], created_at=CREATED,
        updated_at=CREATED, legs=list(legs), stays=list(stays), timeline=[], warnings=[],
    )


def _kinds(reminders):
    return [r.kind for r in reminders]


class TestTripStart:
    @pytest.mark.parametrize("days", [7, 3, 1])
    def test_reminds_on_the_configured_days(self, days):
        today = date(2026, 12, 17) - timedelta(days=days)
        reminders = build_travel_reminders([_trip()], _utc(10, 9), today, SETTINGS)
        assert _kinds(reminders) == ["travel_trip_start"]
        assert f"starts in {days} day" in reminders[0].text

    def test_singular_day(self):
        text = build_travel_reminders([_trip()], _utc(16, 9), date(2026, 12, 16), SETTINGS)[0].text
        assert text.endswith("starts in 1 day")

    def test_silent_on_other_days(self):
        assert build_travel_reminders([_trip()], _utc(13, 9), date(2026, 12, 13), SETTINGS) == []

    def test_mentions_the_checklist_note(self):
        reminders = build_travel_reminders([_trip(checklist_note_id=42)], _utc(10, 9), date(2026, 12, 10), SETTINGS)
        assert "note #42" in reminders[0].text


class TestCheckIn:
    def test_window_opens_24h_before_departure(self):
        trip = _trip(legs=[_leg()])  # departs 17th 12:00
        assert "travel_check_in" not in _kinds(build_travel_reminders([trip], _utc(16, 11, 59), date(2026, 12, 16), SETTINGS))
        reminders = build_travel_reminders([trip], _utc(16, 12), date(2026, 12, 16), SETTINGS)
        assert "travel_check_in" in _kinds(reminders)
        assert "XX 123" in [r for r in reminders if r.kind == "travel_check_in"][0].text

    def test_closes_at_departure(self):
        trip = _trip(legs=[_leg()])
        assert "travel_check_in" not in _kinds(build_travel_reminders([trip], _utc(17, 12), date(2026, 12, 17), SETTINGS))

    def test_only_for_flights(self):
        trip = _trip(legs=[_leg(mode="train")])
        assert "travel_check_in" not in _kinds(build_travel_reminders([trip], _utc(16, 20), date(2026, 12, 16), SETTINGS))

    def test_spans_midnight_so_dedups_over_two_days(self):
        reminders = build_travel_reminders([_trip(legs=[_leg()])], _utc(16, 20), date(2026, 12, 16), SETTINGS)
        assert [r for r in reminders if r.kind == "travel_check_in"][0].dedup_days == 2


class TestLeaveHome:
    def test_announced_an_hour_ahead_of_the_leave_time(self):
        trip = _trip(legs=[_leg()])  # leave at 12:00 - 3h = 09:00
        assert "travel_leave_home" not in _kinds(build_travel_reminders([trip], _utc(17, 7, 59), date(2026, 12, 17), SETTINGS))
        reminders = build_travel_reminders([trip], _utc(17, 8), date(2026, 12, 17), SETTINGS)
        leave = [r for r in reminders if r.kind == "travel_leave_home"][0]
        assert "by 09:00" in leave.text and "departs 12:00" in leave.text

    def test_stops_after_departure(self):
        trip = _trip(legs=[_leg()])
        assert "travel_leave_home" not in _kinds(build_travel_reminders([trip], _utc(17, 12, 30), date(2026, 12, 17), SETTINGS))

    def test_only_for_the_first_leg_of_the_trip(self):
        later = _leg(id=2, departs=_utc(20, 12))
        trip = _trip(legs=[_leg(mode="train"), later])
        assert "travel_leave_home" not in _kinds(build_travel_reminders([trip], _utc(20, 8), date(2026, 12, 20), SETTINGS))

    def test_uses_the_settings(self):
        trip = _trip(legs=[_leg()])
        short = TravelSettingsRead(airport_buffer_min=30, home_to_airport_min=30)  # leave at 11:00
        assert "travel_leave_home" not in _kinds(build_travel_reminders([trip], _utc(17, 9), date(2026, 12, 17), short))
        assert "travel_leave_home" in _kinds(build_travel_reminders([trip], _utc(17, 10), date(2026, 12, 17), short))


class TestCheckOut:
    def test_on_check_out_day_before_check_out(self):
        trip = _trip(stays=[_stay()])  # out on the 19th 10:00
        reminders = build_travel_reminders([trip], _utc(19, 8), date(2026, 12, 19), SETTINGS)
        assert _kinds(reminders) == ["travel_check_out"]
        assert "Hotel Example at 10:00" in reminders[0].text

    def test_not_after_check_out_or_on_other_days(self):
        trip = _trip(stays=[_stay()])
        assert build_travel_reminders([trip], _utc(19, 10, 30), date(2026, 12, 19), SETTINGS) == []
        assert build_travel_reminders([trip], _utc(18, 8), date(2026, 12, 18), SETTINGS) == []

    def test_check_out_day_is_judged_in_the_hotel_zone(self):
        stay = _stay(check_in=_utc(17, 15), check_out=datetime(2026, 12, 19, 8, 0, tzinfo=timezone.utc))
        stay = stay.model_copy(update={"timezone": "Asia/Tokyo"})  # check-out 17:00 on the 19th local
        # 20:00 UTC on the 18th is 05:00 on the 19th in Tokyo: already check-out day there
        reminders = build_travel_reminders([_trip(stays=[stay])], datetime(2026, 12, 18, 20, tzinfo=timezone.utc), date(2026, 12, 18), SETTINGS)
        assert _kinds(reminders) == ["travel_check_out"]


class TestLeaveHomeTimeline:
    def test_none_without_legs_or_when_first_leg_is_not_a_flight(self):
        assert leave_home_at([], 180) is None
        assert leave_home_at([_leg(mode="train")], 180) is None

    def test_first_flight_minus_buffer(self):
        assert leave_home_at([_leg(), _leg(id=2, departs=_utc(20, 9))], 180) == _utc(17, 9)

    def test_timeline_has_a_leave_home_item_before_the_flight(self):
        legs = [_leg()]
        items = build_timeline(legs, [], leave_home_at(legs, 180))
        assert [i.kind for i in items] == ["leave_home", "leg", "arrival"]
        assert items[0].local.hour == 9


class TestSettingsService:
    @pytest.fixture
    def service(self):
        svc = TravelSettingsService(AsyncMock())
        svc._settings = SimpleNamespace(get_value=AsyncMock(return_value=None), set_value=AsyncMock())
        return svc

    async def test_defaults_when_nothing_is_stored(self, service):
        settings = await service.get()
        assert (settings.airport_buffer_min, settings.home_to_airport_min) == (
            DEFAULT_AIRPORT_BUFFER_MIN, DEFAULT_HOME_TO_AIRPORT_MIN,
        )

    async def test_reads_stored_values(self, service):
        service._settings.get_value.side_effect = lambda key, default=None: {"travel.airport_buffer_min": "90"}.get(key)
        assert (await service.get()).airport_buffer_min == 90

    async def test_update_stores_only_the_given_fields(self, service):
        await service.update(TravelSettingsUpdate(home_to_airport_min=30))
        service._settings.set_value.assert_awaited_once_with("travel.home_to_airport_min", "30")

    def test_update_rejects_negative_values(self):
        with pytest.raises(ValueError):
            TravelSettingsUpdate(airport_buffer_min=-1)


class TestTravelReminderService:
    async def test_loads_trips_in_the_window_and_builds_candidates(self):
        svc = TravelReminderService(AsyncMock())
        svc._repo = AsyncMock()
        svc._trips = AsyncMock()
        svc._settings = AsyncMock()
        svc._repo.get_trips_in_window.return_value = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        svc._trips.get_trip_detail.side_effect = [_trip(), None]
        svc._settings.get.return_value = SETTINGS
        with patch("app.features.travel.reminders.local_now", return_value=datetime(2026, 12, 10, 9, tzinfo=timezone.utc)):
            reminders = await svc.get_reminders()
        assert _kinds(reminders) == ["travel_trip_start"]
        first_day, last_day = svc._repo.get_trips_in_window.await_args.args
        assert (first_day, last_day) == (date(2026, 12, 10), date(2026, 12, 17))


class TestSchedulerIntegration:
    async def _lines(self, reminders, reminded_keys=()):
        svc = ReminderService(AsyncMock(), AsyncMock())
        svc._travel_reminder_service = SimpleNamespace(get_reminders=AsyncMock(return_value=reminders))
        svc._working_memory_repo = SimpleNamespace(
            list=AsyncMock(side_effect=lambda f: [MagicMock()] if f.key in reminded_keys else []),
            upsert=AsyncMock(),
        )
        return await svc._collect_travel_lines(date(2026, 12, 10)), svc._working_memory_repo.upsert

    async def test_lines_are_prefixed_and_marked(self):
        lines, upsert = await self._lines([TravelReminder("travel_trip_start", 1, "Trip starts")])
        assert lines == ["✈️ Trip starts"]
        assert upsert.call_args[0][0].key == "reminder:travel_trip_start:1:2026-12-10"

    async def test_already_reminded_today_is_skipped(self):
        lines, upsert = await self._lines(
            [TravelReminder("travel_trip_start", 1, "x")], reminded_keys={"reminder:travel_trip_start:1:2026-12-10"}
        )
        assert lines == [] and not upsert.await_count

    async def test_two_day_window_also_checks_yesterday(self):
        reminder = TravelReminder("travel_check_in", 5, "x", dedup_days=2)
        lines, _ = await self._lines([reminder], reminded_keys={"reminder:travel_check_in:5:2026-12-09"})
        assert lines == []
