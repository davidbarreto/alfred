import re
from datetime import datetime, timedelta, timezone as dt_timezone

from dateutil.rrule import rrulestr

from app.shared.timezone import local_timezone

_MAX_OCCURRENCES = 366
_UNBOUNDED_HORIZON = timedelta(days=365 * 5)
_UNTIL_UTC_RE = re.compile(r"(UNTIL=)(\d{8}T\d{6})Z")


def _localize_until(recurrence_rule: str) -> str:
    """Rewrite a `Z`-suffixed (UTC) UNTIL token to naive local time.

    Google Calendar always encodes UNTIL in UTC, but LocalDateTime hands this
    module naive local datetimes for dtstart/end_datetime, so dateutil.rrule
    would otherwise reject the aware/naive tzinfo mismatch.
    """

    def _replace(match: re.Match[str]) -> str:
        until_utc = datetime.strptime(match.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=dt_timezone.utc)
        until_local = until_utc.astimezone(local_timezone()).replace(tzinfo=None)
        return f"{match.group(1)}{until_local.strftime('%Y%m%dT%H%M%S')}"

    return _UNTIL_UTC_RE.sub(_replace, recurrence_rule)


def expand_occurrences(
    start_datetime: datetime,
    end_datetime: datetime,
    recurrence_rule: str,
    range_start: datetime | None,
    range_end: datetime | None,
) -> list[tuple[datetime, datetime]]:
    """Expand a series' RRULE into (start, end) pairs overlapping [range_start, range_end]."""
    duration = end_datetime - start_datetime
    rule = rrulestr(_localize_until(recurrence_rule), dtstart=start_datetime)

    after = start_datetime if range_start is None else max(start_datetime, range_start - duration)
    before = (start_datetime + _UNBOUNDED_HORIZON) if range_end is None else range_end

    starts = rule.between(after, before, inc=True)
    return [(s, s + duration) for s in starts[:_MAX_OCCURRENCES]]
