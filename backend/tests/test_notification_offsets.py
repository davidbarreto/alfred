from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from app.shared.notification_offsets import parse_offset


class TestParseOffset:
    def test_zero_is_no_offset(self):
        assert parse_offset("0") == timedelta()

    def test_days(self):
        assert parse_offset("7d") == timedelta(days=7)

    def test_hours(self):
        assert parse_offset("4h") == timedelta(hours=4)

    def test_minutes(self):
        assert parse_offset("30m") == timedelta(minutes=30)

    def test_months_is_relativedelta(self):
        assert parse_offset("1mo") == relativedelta(months=1)

    def test_months_is_calendar_exact_not_thirty_days(self):
        # 1 month before Mar 31 lands on Feb 28 (or 29), not "31 - 30 days".
        result = date(2026, 3, 31) - parse_offset("1mo")
        assert result == date(2026, 2, 28)

    def test_invalid_unit_raises(self):
        with pytest.raises(ValueError):
            parse_offset("7x")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            parse_offset("abc")
