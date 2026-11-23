from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from app.shared.utils.time_text import (
    WEEKDAYS,
    format_clock,
    format_weekdays,
    parse_clock,
    parse_offset,
    parse_weekday,
    weekday_key,
    weekday_range,
)


class TestWeekdays:
    def test_weekday_key(self):
        assert weekday_key(date(2026, 11, 23)) == "mon"
        assert weekday_key(date(2026, 11, 29)) == "sun"
        assert WEEKDAYS[0] == "mon" and len(WEEKDAYS) == 7

    @pytest.mark.parametrize("token, key", [("mon", "mon"), ("Monday", "mon"), (" THURS ", "thu"), ("sunday", "sun")])
    def test_parse_weekday(self, token, key):
        assert parse_weekday(token) == key

    def test_parse_weekday_unknown(self):
        with pytest.raises(ValueError, match="'funday' is not a day"):
            parse_weekday("funday")

    def test_range_and_wrap(self):
        assert weekday_range("mon", "wed") == ["mon", "tue", "wed"]
        assert weekday_range("fri", "mon") == ["fri", "sat", "sun", "mon"]
        assert weekday_range("sat", "sat") == ["sat"]

    def test_format_runs(self):
        assert format_weekdays(["fri", "mon", "tue", "wed"]) == "mon-wed,fri"
        assert format_weekdays(["sun"]) == "sun"
        assert format_weekdays(["sat", "sun", "mon"]) == "mon,sat-sun"
        assert format_weekdays([]) == ""


class TestClock:
    @pytest.mark.parametrize("value, minutes", [("0", 0), ("8", 480), ("8:05", 485), ("08:30", 510), ("24:00", 1440)])
    def test_parse(self, value, minutes):
        assert parse_clock(value) == minutes

    @pytest.mark.parametrize("value, message", [
        ("8am", "not a time"), ("8:5", "not a time"), ("25", "not a time of day"), ("10:60", "not a time of day"),
        ("24:01", "not a time of day"),
    ])
    def test_parse_bad(self, value, message):
        with pytest.raises(ValueError, match=message):
            parse_clock(value)

    def test_format(self):
        assert format_clock(0) == "00:00"
        assert format_clock(485) == "08:05"
        assert format_clock(1440) == "24:00"


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
