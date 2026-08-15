"""Finance "month" cycle math, shared by transactions period resolution and budgets.

A cycle runs from `cycle_start_day` of one month through `cycle_start_day - 1` of the
next, and is labeled by the calendar month it starts in (e.g. cycle_start_day=25 means
"August" is Aug 25 - Sep 24). cycle_start_day=1 reproduces a plain calendar month.
"""
import calendar
from datetime import date, timedelta


def _clamp_day(year: int, month: int, day: int) -> int:
    return min(day, calendar.monthrange(year, month)[1])


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    total = (month - 1) + delta
    return year + total // 12, total % 12 + 1


def current_cycle_range(reference: date, cycle_start_day: int = 1) -> tuple[date, date]:
    """The [start, end] of the cycle containing `reference`."""
    start_day_this_month = _clamp_day(reference.year, reference.month, cycle_start_day)
    if reference.day >= start_day_this_month:
        start_year, start_month = reference.year, reference.month
    else:
        start_year, start_month = _add_months(reference.year, reference.month, -1)
    start = date(start_year, start_month, _clamp_day(start_year, start_month, cycle_start_day))

    end_year, end_month = _add_months(start_year, start_month, 1)
    end = date(end_year, end_month, _clamp_day(end_year, end_month, cycle_start_day)) - timedelta(days=1)
    return start, end


def previous_cycle_range(reference: date, cycle_start_day: int = 1) -> tuple[date, date]:
    """The cycle immediately before the one containing `reference`."""
    start, _ = current_cycle_range(reference, cycle_start_day)
    return current_cycle_range(start - timedelta(days=1), cycle_start_day)


def parse_year_month_reference(year_month: str | None, cycle_start_day: int) -> date:
    """Turn a "YYYY-MM" label into a reference date inside the cycle that label
    identifies, or today's date (inside today's active cycle) when omitted."""
    if year_month is None:
        return date.today()
    try:
        year, month = (int(part) for part in year_month.split("-", 1))
        return date(year, month, _clamp_day(year, month, cycle_start_day))
    except (ValueError, TypeError):
        raise ValueError("year_month must be in YYYY-MM format")
