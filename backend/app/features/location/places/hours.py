"""Opening hours: one text form for people, one JSON form for storage, and the lookups between them.

JSON: {"mon": [["08:00", "20:00"]], ..., "sun": [], "hol": [["09:00", "13:00"]]}. A missing key is unknown,
an empty list is closed, several ranges allow a lunch break. "hol" holds the public-holiday hours.

Text: segments separated by ";" or new lines, each "<days> <ranges>":
    mon-fri 08:00-20:00; sat 09:00-13:00, 15:00-19:00; sun closed; holidays closed
Days are names (mon or monday), ranges of them (mon-fri, fri-mon wraps), comma lists (mon,wed), "daily",
or "holidays". Ranges are H[:MM]-H[:MM] (24:00 allowed as an end), or "closed".

Pure functions, shared by the API, the portal form (through the API) and the command.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time

from app.shared.utils.time_text import (
    MINUTES_PER_DAY,
    WEEKDAYS,
    format_clock,
    format_weekdays,
    parse_clock,
    parse_weekday,
    weekday_key,
    weekday_range,
)

HOLIDAY_KEY = "hol"
KEYS: tuple[str, ...] = (*WEEKDAYS, HOLIDAY_KEY)

_HOLIDAY_NAMES = {"hol", "holiday", "holidays"}
_DAILY_NAMES = {"daily", "everyday"}
_CLOSED = "closed"
_SEGMENT = re.compile(r"^(?P<days>.+?)\s+(?P<ranges>closed|\d.*)$", re.IGNORECASE)

Ranges = list[list[str]]
Hours = dict[str, Ranges]


class HoursError(ValueError):
    """Opening hours that cannot be read; the message says which part and why."""


def _minutes(value: str) -> int:
    try:
        return parse_clock(value)
    except ValueError as exc:
        raise HoursError(str(exc)) from exc


def _clean_ranges(pairs: list[tuple[str, str]]) -> Ranges:
    """Validated, sorted, zero-padded ranges; overlapping or empty ranges are refused."""
    spans = []
    for start, end in pairs:
        begin, finish = _minutes(start), _minutes(end)
        if begin >= MINUTES_PER_DAY:
            raise HoursError(f"{start!r} is not a time of day")
        if finish <= begin:
            raise HoursError(f"{start}-{end} must end after it starts (overnight hours are not supported)")
        spans.append((begin, finish))
    spans.sort()
    for (_, previous_end), (next_start, _) in zip(spans, spans[1:]):
        if next_start < previous_end:
            raise HoursError("opening ranges overlap")
    return [[format_clock(begin), format_clock(finish)] for begin, finish in spans]


def _parse_ranges(text: str) -> Ranges:
    if text.strip().lower() == _CLOSED:
        return []
    pairs = []
    for token in (t for t in re.split(r"[,\s]+", text.strip()) if t):
        if token.count("-") != 1:
            raise HoursError(f"{token!r} is not a range (use 08:00-20:00)")
        start, end = token.split("-")
        pairs.append((start, end))
    return _clean_ranges(pairs)


def _parse_days(text: str) -> list[str]:
    keys: list[str] = []
    for token in (t for t in re.split(r"[,\s]+", text.strip().lower()) if t):
        try:
            if token in _DAILY_NAMES:
                keys.extend(WEEKDAYS)
            elif token in _HOLIDAY_NAMES:
                keys.append(HOLIDAY_KEY)
            elif "-" in token:
                first, _, last = token.partition("-")
                keys.extend(weekday_range(first, last))
            else:
                keys.append(parse_weekday(token))
        except ValueError as exc:
            raise HoursError(f"{token!r} is not a day (use mon, tue, ... sun, daily or holidays)") from exc
    return keys


def parse_hours(text: str | None) -> Hours | None:
    """Text form to the JSON form; blank text is None (hours unknown)."""
    if text is None or not text.strip():
        return None
    result: Hours = {}
    normalized = text.replace("–", "-").replace("—", "-")
    for segment in (s.strip() for s in re.split(r"[;\n]+", normalized)):
        if not segment:
            continue
        match = _SEGMENT.match(segment)
        if not match:
            raise HoursError(f"{segment!r} needs days then hours, like 'mon-fri 08:00-20:00' or 'sun closed'")
        ranges = _parse_ranges(match.group("ranges"))
        # A range like "mon-fri" is split from the times by the first space, so "mon - fri" needs joining.
        days_text = re.sub(r"\s*-\s*", "-", match.group("days"))
        for key in _parse_days(days_text):
            if key in result:
                raise HoursError(f"{_label(key)} is given more than once")
            result[key] = ranges
    return result


def normalize_hours(value: str | dict | None) -> Hours | None:
    """The stored JSON form from either form: text is parsed, a dict is checked and cleaned."""
    if value is None or isinstance(value, str):
        return parse_hours(value)
    if not isinstance(value, dict):
        raise HoursError("opening hours must be text or an object of days")
    result: Hours = {}
    for key, ranges in value.items():
        if key not in KEYS:
            raise HoursError(f"{key!r} is not a day (use {', '.join(KEYS)})")
        if not isinstance(ranges, list) or any(
            not isinstance(pair, (list, tuple)) or len(pair) != 2 or not all(isinstance(v, str) for v in pair)
            for pair in ranges
        ):
            raise HoursError(f"{key} must be a list of [start, end] times")
        result[key] = _clean_ranges([(start, end) for start, end in ranges])
    return {key: result[key] for key in KEYS if key in result} or None


def format_ranges(ranges: Ranges | None) -> str | None:
    """"08:00-13:00, 14:00-19:00", "closed", or None when unknown."""
    if ranges is None:
        return None
    if not ranges:
        return _CLOSED
    return ", ".join(f"{start}-{end}" for start, end in ranges)


def _label(key: str) -> str:
    return "holidays" if key == HOLIDAY_KEY else key


def format_hours(hours: Hours | None) -> str:
    """JSON form to the text form ("" when unknown); parse_hours(format_hours(x)) == x."""
    if not hours:
        return ""
    groups: dict[str, list[str]] = {}
    for day in WEEKDAYS:
        if day in hours:
            groups.setdefault(format_ranges(hours[day]), []).append(day)
    segments = []
    for text, days in groups.items():
        label = "daily" if len(days) == len(WEEKDAYS) else format_weekdays(days)
        segments.append(f"{label} {text}")
    if HOLIDAY_KEY in hours:
        segments.append(f"holidays {format_ranges(hours[HOLIDAY_KEY])}")
    return "; ".join(segments)


@dataclass(frozen=True)
class DayHours:
    """The hours that apply on one date: ranges (None = unknown, [] = closed), and whether a holiday set them."""

    ranges: Ranges | None
    holiday: bool = False
    holiday_hours_known: bool = True


def hours_on(hours: Hours | None, day: date, holiday: bool) -> DayHours:
    """Holiday hours on a holiday when they are known, else the weekday's hours (flagged as a guess)."""
    hours = hours or {}
    weekday = hours.get(weekday_key(day))
    if not holiday:
        return DayHours(weekday)
    if HOLIDAY_KEY in hours:
        return DayHours(hours[HOLIDAY_KEY], holiday=True)
    return DayHours(weekday, holiday=True, holiday_hours_known=False)


def open_at(ranges: Ranges | None, moment: time) -> bool | None:
    """Whether a time falls inside one of the ranges; None when the hours are unknown."""
    if ranges is None:
        return None
    minute = moment.hour * 60 + moment.minute
    return any(_minutes(start) <= minute < _minutes(end) for start, end in ranges)
