from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def purchase_days(bought_at: list[datetime], tz: ZoneInfo) -> list[date]:
    """Distinct local calendar days on which something was bought, oldest first.

    Several entries ticked off in one shop (or one evening) are one purchase, not several."""
    return sorted({moment.astimezone(tz).date() for moment in bought_at})


def average_interval_days(days: list[date]) -> float | None:
    """Mean number of days between consecutive purchase days; None with fewer than two."""
    if len(days) < 2:
        return None
    return (days[-1] - days[0]).days / (len(days) - 1)


def next_expected_on(last: date, average_days: float) -> date:
    return last + timedelta(days=round(average_days))
