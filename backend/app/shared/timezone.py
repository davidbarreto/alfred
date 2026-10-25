from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def local_timezone_name() -> str:
    return get_settings().timezone


def local_now() -> datetime:
    return datetime.now(local_timezone())


def local_today() -> date:
    """Today's calendar date in the configured timezone (never the server's)."""
    return local_now().date()


def local_naive_now() -> datetime:
    """Current local wall-clock time without tzinfo, matching what LocalDateTime columns return."""
    return local_now().replace(tzinfo=None)
