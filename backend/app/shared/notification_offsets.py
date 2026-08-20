import re
from datetime import timedelta

from dateutil.relativedelta import relativedelta

_OFFSET_PATTERN = re.compile(r"^(\d+)(mo|[dhm])$")


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
