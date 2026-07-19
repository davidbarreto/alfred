from datetime import datetime, timedelta

from dateutil.rrule import rrulestr

_MAX_OCCURRENCES = 366
_UNBOUNDED_HORIZON = timedelta(days=365 * 5)


def expand_occurrences(
    start_datetime: datetime,
    end_datetime: datetime,
    recurrence_rule: str,
    range_start: datetime | None,
    range_end: datetime | None,
) -> list[tuple[datetime, datetime]]:
    """Expand a series' RRULE into (start, end) pairs overlapping [range_start, range_end]."""
    duration = end_datetime - start_datetime
    rule = rrulestr(recurrence_rule, dtstart=start_datetime)

    after = start_datetime if range_start is None else max(start_datetime, range_start - duration)
    before = (start_datetime + _UNBOUNDED_HORIZON) if range_end is None else range_end

    starts = rule.between(after, before, inc=True)
    return [(s, s + duration) for s in starts[:_MAX_OCCURRENCES]]
