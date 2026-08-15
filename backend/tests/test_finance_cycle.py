from datetime import date

import pytest

from app.features.finance.cycle import (
    current_cycle_range,
    parse_year_month_reference,
    previous_cycle_range,
)


class TestCurrentCycleRangeDefaultStartDay:
    def test_regular_month(self):
        start, end = current_cycle_range(date(2026, 7, 10))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)

    def test_december_rollover(self):
        start, end = current_cycle_range(date(2026, 12, 5))
        assert start == date(2026, 12, 1)
        assert end == date(2026, 12, 31)


class TestCurrentCycleRangeCustomStartDay:
    def test_before_start_day_belongs_to_previous_month_cycle(self):
        start, end = current_cycle_range(date(2026, 8, 15), cycle_start_day=25)
        assert start == date(2026, 7, 25)
        assert end == date(2026, 8, 24)

    def test_on_start_day_belongs_to_this_month_cycle(self):
        start, end = current_cycle_range(date(2026, 8, 25), cycle_start_day=25)
        assert start == date(2026, 8, 25)
        assert end == date(2026, 9, 24)

    def test_december_rollover_custom_start_day(self):
        start, end = current_cycle_range(date(2026, 12, 27), cycle_start_day=25)
        assert start == date(2026, 12, 25)
        assert end == date(2027, 1, 24)

    def test_february_clamp(self):
        # cycle_start_day=30 doesn't exist in February -> clamps to the 28th (2026 is not a leap year)
        start, end = current_cycle_range(date(2026, 2, 15), cycle_start_day=30)
        assert start == date(2026, 1, 30)
        assert end == date(2026, 2, 27)


class TestPreviousCycleRange:
    def test_default_start_day(self):
        start, end = previous_cycle_range(date(2026, 7, 10))
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_custom_start_day(self):
        start, end = previous_cycle_range(date(2026, 8, 15), cycle_start_day=25)
        assert start == date(2026, 6, 25)
        assert end == date(2026, 7, 24)


class TestParseYearMonthReference:
    def test_none_returns_today(self):
        assert parse_year_month_reference(None, cycle_start_day=25) == date.today()

    def test_parses_label_into_cycle_start_day(self):
        result = parse_year_month_reference("2026-08", cycle_start_day=25)
        assert result == date(2026, 8, 25)

    def test_clamps_when_start_day_invalid_for_month(self):
        result = parse_year_month_reference("2026-02", cycle_start_day=30)
        assert result == date(2026, 2, 28)

    def test_invalid_format_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_year_month_reference("not-a-date", cycle_start_day=1)

    def test_invalid_month_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_year_month_reference("2026-13", cycle_start_day=1)
