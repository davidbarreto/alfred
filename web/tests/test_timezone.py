from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.routes.watcher import _local_date
from app.shared.timezone import local_today


class TestLocalToday:
    def test_uses_configured_timezone_not_server_date(self):
        fixed = datetime(2026, 7, 16, 0, 30, tzinfo=ZoneInfo("Europe/Lisbon"))
        with patch("app.shared.timezone.local_now", return_value=fixed):
            assert local_today().isoformat() == "2026-07-16"


class TestWatcherLocalDate:
    def test_utc_timestamp_after_local_midnight_belongs_to_next_day(self):
        # 23:30 UTC in July is 00:30 the next day in Lisbon (WEST)
        assert _local_date("2026-07-15T23:30:00+00:00") == "2026-07-16"

    def test_naive_timestamp_is_treated_as_utc(self):
        assert _local_date("2026-07-15T23:30:00") == "2026-07-16"

    def test_winter_timestamp_keeps_utc_date(self):
        assert _local_date("2026-12-15T23:30:00+00:00") == "2026-12-15"
