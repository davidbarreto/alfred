"""Time values written as text: weekday keys and names, HH:MM <-> minutes since midnight, and offsets like "7d".

Pure functions with no timezone logic (see `timezone.py` for "now" and "today"). Bad input raises ValueError
with a message fit to show the user.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
MINUTES_PER_DAY = 24 * 60

_WEEKDAY_NAMES = {
    **{d: d for d in WEEKDAYS},
    "monday": "mon", "tuesday": "tue", "tues": "tue", "wednesday": "wed", "thursday": "thu", "thur": "thu",
    "thurs": "thu", "friday": "fri", "saturday": "sat", "sunday": "sun",
}
_CLOCK = re.compile(r"^(\d{1,2})(?::(\d{2}))?$")
_OFFSET_PATTERN = re.compile(r"^(\d+)(mo|[dhm])$")


def weekday_key(day: date) -> str:
    """"mon" ... "sun" for a date."""
    return WEEKDAYS[day.weekday()]


def parse_weekday(token: str) -> str:
    """A weekday key from a short or full name, any case ("Monday" -> "mon")."""
    key = _WEEKDAY_NAMES.get(token.strip().lower())
    if key is None:
        raise ValueError(f"{token!r} is not a day (use mon, tue, ... sun)")
    return key


def weekday_range(first: str, last: str) -> list[str]:
    """Every weekday from first to last inclusive, wrapping past Sunday ("fri", "mon" -> fri, sat, sun, mon)."""
    start, stop = WEEKDAYS.index(parse_weekday(first)), WEEKDAYS.index(parse_weekday(last))
    return [WEEKDAYS[(start + i) % 7] for i in range((stop - start) % 7 + 1)]


def format_weekdays(days: Iterable[str]) -> str:
    """Weekday keys as runs of consecutive days, Monday first, no wrapping: mon,tue,wed,fri -> "mon-wed,fri"."""
    indexes = sorted({WEEKDAYS.index(d) for d in days})
    runs: list[list[int]] = []
    for index in indexes:
        if runs and index == runs[-1][-1] + 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    return ",".join(WEEKDAYS[r[0]] if len(r) == 1 else f"{WEEKDAYS[r[0]]}-{WEEKDAYS[r[-1]]}" for r in runs)


def parse_clock(value: str) -> int:
    """Minutes since midnight from "H", "H:MM" or "HH:MM"; "24:00" is allowed (the end of the day)."""
    match = _CLOCK.match(value.strip())
    if not match:
        raise ValueError(f"{value!r} is not a time (use HH:MM)")
    hours, minutes = int(match.group(1)), int(match.group(2) or 0)
    if minutes > 59 or hours > 24 or (hours == 24 and minutes):
        raise ValueError(f"{value!r} is not a time of day")
    return hours * 60 + minutes


def format_clock(minutes: int) -> str:
    """"HH:MM" for minutes since midnight (1440 -> "24:00")."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_offset(offset: str) -> timedelta | relativedelta:
    """Parse a cascade offset string like "7d", "4h", "30m", "1mo", or "0".

    "mo" is calendar-exact month subtraction (relativedelta), so "1mo before
    Aug 23" lands on Jul 23 regardless of month length. Every other unit is a
    fixed-length timedelta.
    """
    if offset == "0":
        return timedelta()
    match = _OFFSET_PATTERN.match(offset)
    if match is None:
        raise ValueError(f"Invalid notification offset: {offset!r}")
    amount, unit = match.groups()
    amount = int(amount)
    if unit == "mo":
        return relativedelta(months=amount)
    if unit == "d":
        return timedelta(days=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(minutes=amount)
