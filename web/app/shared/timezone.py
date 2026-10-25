from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def local_today() -> date:
    """Today's calendar date in the configured timezone (never the server's)."""
    return local_now().date()
