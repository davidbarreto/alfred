"""What happens at home while a trip lasts: pure rules (this file) and the loader (`while_away_service.py`)."""
from datetime import date
from decimal import Decimal
from typing import Callable

from pydantic import BaseModel

# A rule that never ends would loop forever; one trip never needs more.
_MAX_STEPS = 400


class AwayBirthday(BaseModel):
    contact_id: int
    name: str
    date: date


class AwayTask(BaseModel):
    task_id: int
    title: str
    due: date


class AwayCharge(BaseModel):
    recurring_id: int
    merchant: str | None
    amount: Decimal
    currency: str
    date: date


class WhileAway(BaseModel):
    trip_id: int
    birthdays: list[AwayBirthday]
    tasks: list[AwayTask]
    charges: list[AwayCharge]


def birthdays_between(birthday: date, start: date, end: date) -> list[date]:
    """Each occurrence of an annual birthday inside [start, end]; 29 Feb falls on 1 Mar in other years."""
    found: list[date] = []
    for year in range(start.year, end.year + 1):
        try:
            candidate = birthday.replace(year=year)
        except ValueError:
            candidate = date(year, 3, 1)
        if start <= candidate <= end:
            found.append(candidate)
    return found


def occurrences_between(
    rule: str, last: date | None, start: date, end: date, step: Callable[[str, date], date | None], today: date,
) -> list[date]:
    """Dates a recurring transaction will be created on inside [start, end], from its last created occurrence.

    `step(rule, d)` is the next occurrence after d. A rule never run yet makes its first one on `today`."""
    found: list[date] = []
    current = last if last is not None else today
    if last is None and start <= today <= end:
        found.append(today)
    for _ in range(_MAX_STEPS):
        nxt = step(rule, current)
        if nxt is None or nxt > end:
            break
        if nxt >= start:
            found.append(nxt)
        current = nxt
    return found
