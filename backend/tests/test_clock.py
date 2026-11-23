from datetime import date

import pytest

from app.shared.clock import (
    WEEKDAYS,
    format_clock,
    format_weekdays,
    parse_clock,
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
