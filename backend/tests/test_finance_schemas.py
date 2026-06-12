import pytest
from datetime import date
from unittest.mock import patch
from app.features.finance.transactions.schemas import resolve_period

FIXED_TODAY = date(2026, 6, 12)  # Friday


def _today(d=FIXED_TODAY):
    return patch("app.features.finance.transactions.schemas.date", wraps=date, **{"today.return_value": d})


class TestResolvePeriodExplicitDates:
    def test_explicit_from_and_to_override_period(self):
        from_d = date(2026, 1, 1)
        to_d = date(2026, 1, 31)
        result = resolve_period("this month", from_d, to_d)
        assert result == (from_d, to_d)

    def test_explicit_dates_without_period(self):
        from_d = date(2026, 3, 5)
        to_d = date(2026, 3, 20)
        assert resolve_period(None, from_d, to_d) == (from_d, to_d)


class TestResolvePeriodKeywords:
    def test_this_month(self):
        with _today():
            start, end = resolve_period("this month", None, None)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_current_month_alias(self):
        with _today():
            start, end = resolve_period("current month", None, None)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_last_month(self):
        with _today():
            start, end = resolve_period("last month", None, None)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 31)

    def test_previous_month_alias(self):
        with _today():
            start, end = resolve_period("previous month", None, None)
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 31)

    def test_this_week(self):
        with _today():
            start, end = resolve_period("this week", None, None)
        # 2026-06-12 is Friday (weekday=4), Monday is 2026-06-08
        assert start == date(2026, 6, 8)
        assert end == date(2026, 6, 14)

    def test_last_week(self):
        with _today():
            start, end = resolve_period("last week", None, None)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 7)

    def test_this_year(self):
        with _today():
            start, end = resolve_period("this year", None, None)
        assert start == date(2026, 1, 1)
        assert end == date(2026, 12, 31)

    def test_last_year(self):
        with _today():
            start, end = resolve_period("last year", None, None)
        assert start == date(2025, 1, 1)
        assert end == date(2025, 12, 31)

    def test_today(self):
        with _today():
            start, end = resolve_period("today", None, None)
        assert start == FIXED_TODAY
        assert end == FIXED_TODAY

    def test_yesterday(self):
        with _today():
            start, end = resolve_period("yesterday", None, None)
        assert start == date(2026, 6, 11)
        assert end == date(2026, 6, 11)

    def test_current_week_alias(self):
        with _today():
            start, end = resolve_period("current week", None, None)
        assert start == date(2026, 6, 8)
        assert end == date(2026, 6, 14)

    def test_this_month_december_wraps_year(self):
        december = date(2026, 12, 15)
        with _today(december):
            start, end = resolve_period("this month", None, None)
        assert start == date(2026, 12, 1)
        assert end == date(2026, 12, 31)


class TestResolvePeriodDefault:
    def test_no_period_no_dates_returns_current_month(self):
        with _today():
            start, end = resolve_period(None, None, None)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)

    def test_unknown_period_keyword_falls_through_to_default(self):
        with _today():
            start, end = resolve_period("quarterly", None, None)
        assert start == date(2026, 6, 1)
        assert end == date(2026, 6, 30)
