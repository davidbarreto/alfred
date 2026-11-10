"""Helpers for instants stored in UTC alongside the IANA zone they were entered in."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise ValueError(f"Unknown time zone: {name!r}") from exc
    return name


def to_utc(value: datetime, zone: str) -> datetime:
    """An aware value is converted as is; a naive one is read as wall time in `zone`."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(zone))
    return value.astimezone(timezone.utc)


def to_local(value: datetime, zone: str) -> datetime:
    """The naive wall-clock time of an instant in `zone`."""
    return value.astimezone(ZoneInfo(zone)).replace(tzinfo=None)
