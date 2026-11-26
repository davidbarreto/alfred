"""Pure helpers over residence periods: half-open date ranges, "since birth" and "still there" as open ends."""
from datetime import date
from typing import Protocol


class Period(Protocol):
    from_date: date | None
    to_date: date | None
    born: bool


def bounds(period: Period) -> tuple[date, date]:
    """[start, end): a null start is the beginning of time, a null end the end of it."""
    return period.from_date or date.min, period.to_date or date.max


def overlaps(a: Period, b: Period) -> bool:
    a_start, a_end = bounds(a)
    b_start, b_end = bounds(b)
    return a_start < b_end and b_start < a_end


def lived_on(day: date, periods: list[Period]) -> bool:
    return any(start <= day < end for start, end in map(bounds, periods))


def lived_summary(periods: list[Period]) -> dict:
    """What a city's or country's residences say about it: born there, living there (since the start of the unbroken
    run of rows that ends in the open one; None when that run starts at birth), or lived there until a date."""
    if not periods:
        return {}
    rows = sorted(periods, key=lambda p: bounds(p)[0])
    born = any(p.born for p in rows)
    current = next((p for p in rows if p.to_date is None), None)
    if current is None:
        return {"born": born, "lived_until": max(p.to_date for p in rows)}
    since = current.from_date
    for earlier in reversed(rows[:rows.index(current)]):
        if since is None or earlier.to_date is None or earlier.to_date < since:
            break
        since = earlier.from_date
    return {"born": born, "living": True, "lived_since": since}
