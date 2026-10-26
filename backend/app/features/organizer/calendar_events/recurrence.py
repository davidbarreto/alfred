import re
from datetime import date, datetime, time, timedelta, timezone as dt_timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dateutil.rrule import rrulestr

from app.shared.timezone import local_timezone

_MAX_OCCURRENCES = 366
_UNBOUNDED_HORIZON = timedelta(days=365 * 5)
_UNTIL_UTC_RE = re.compile(r"(UNTIL=)(\d{8}T\d{6})Z")
_END_PARTS_RE = re.compile(r"(?:^|;)(?:UNTIL|COUNT)=[^;]*")


def _localize_until(recurrence_rule: str, zone: tzinfo) -> str:
    """Rewrite a `Z`-suffixed (UTC) UNTIL token to naive wall time in `zone`.

    Google Calendar always encodes UNTIL in UTC, but the series is expanded as
    naive wall-clock datetimes, so dateutil.rrule would otherwise reject the
    aware/naive tzinfo mismatch.
    """

    def _replace(match: re.Match[str]) -> str:
        until_utc = datetime.strptime(match.group(2), "%Y%m%dT%H%M%S").replace(tzinfo=dt_timezone.utc)
        until_wall = until_utc.astimezone(zone).replace(tzinfo=None)
        return f"{match.group(1)}{until_wall.strftime('%Y%m%dT%H%M%S')}"

    return _UNTIL_UTC_RE.sub(_replace, recurrence_rule)


def _series_zone(event_timezone: str | None) -> tzinfo:
    """The zone a series keeps its wall time in: the event's own, else the app's local zone."""
    if event_timezone:
        try:
            return ZoneInfo(event_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return local_timezone()


def _wall_in(naive_local: datetime, zone: tzinfo) -> datetime:
    return naive_local.replace(tzinfo=local_timezone()).astimezone(zone).replace(tzinfo=None)


def _local_from(wall: datetime, zone: tzinfo) -> datetime:
    return wall.replace(tzinfo=zone).astimezone(local_timezone()).replace(tzinfo=None)


def expand_occurrences(
    start_datetime: datetime,
    end_datetime: datetime,
    recurrence_rule: str,
    range_start: datetime | None,
    range_end: datetime | None,
    event_timezone: str | None = None,
) -> list[tuple[datetime, datetime]]:
    """Expand a series' RRULE into (start, end) pairs overlapping [range_start, range_end].

    Datetimes in and out are naive local time. The series repeats at the same wall time
    in `event_timezone` (the app's zone when omitted), so an event set in another zone
    moves in local time when either zone changes its clocks.
    """
    zone = _series_zone(event_timezone)
    start_wall = _wall_in(start_datetime, zone)
    # Absolute length: subtracting wall times would be off by an hour across a clock change.
    duration = end_datetime.replace(tzinfo=local_timezone()).astimezone(dt_timezone.utc) - start_datetime.replace(
        tzinfo=local_timezone()
    ).astimezone(dt_timezone.utc)
    rule = rrulestr(_localize_until(recurrence_rule, zone), dtstart=start_wall)

    after = start_wall if range_start is None else max(start_wall, _wall_in(range_start, zone) - duration)
    before = (start_wall + _UNBOUNDED_HORIZON) if range_end is None else _wall_in(range_end, zone)

    spans = []
    for wall in rule.between(after, before, inc=True)[:_MAX_OCCURRENCES]:
        start_utc = wall.replace(tzinfo=zone).astimezone(dt_timezone.utc)
        spans.append((_local_from(wall, zone), (start_utc + duration).astimezone(local_timezone()).replace(tzinfo=None)))
    return spans


def end_rule_before(recurrence_rule: str, first_excluded_day: date, all_day: bool) -> str:
    """The rule with any UNTIL/COUNT replaced so the last occurrence is the one before `first_excluded_day`.

    Google wants UNTIL as a date for all-day series and as a UTC instant for timed ones.
    """
    base = _END_PARTS_RE.sub("", recurrence_rule).lstrip(";")
    if all_day:
        until = (first_excluded_day - timedelta(days=1)).strftime("%Y%m%d")
    else:
        midnight = datetime.combine(first_excluded_day, time.min, tzinfo=local_timezone())
        until = (midnight - timedelta(seconds=1)).astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{base};UNTIL={until}"
