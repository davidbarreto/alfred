from datetime import date, datetime

from freezegun import freeze_time

from app.shared.timezone import local_naive_now, local_today


class TestLocalToday:
    @freeze_time("2026-07-15 23:30:00")
    def test_returns_local_date_after_local_midnight(self):
        # 23:30 UTC is 00:30 the next day in Lisbon (WEST, UTC+1)
        assert local_today() == date(2026, 7, 16)
        assert date.today() == date(2026, 7, 15)

    @freeze_time("2026-12-15 23:30:00")
    def test_matches_utc_date_in_winter(self):
        assert local_today() == date(2026, 12, 15)

    @freeze_time("2026-10-25 00:30:00")
    def test_on_the_day_the_clocks_go_back(self):
        # 00:30 UTC is still 01:30 WEST; local date is the same day
        assert local_today() == date(2026, 10, 25)


class TestLocalNaiveNow:
    @freeze_time("2026-07-15 23:30:00")
    def test_is_naive_local_time(self):
        now = local_naive_now()
        assert now.tzinfo is None
        assert now == datetime(2026, 7, 16, 0, 30)


class TestRelativeDatesUseLocalTime:
    @freeze_time("2026-07-15 23:30:00")
    def test_today_resolves_to_local_date_after_local_midnight(self):
        from app.assistant.commands.resolver import _normalize_date

        # server clock (UTC) still says Jul 15; the user's Lisbon clock says Jul 16
        assert _normalize_date("today") == "2026-07-16"
