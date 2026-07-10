from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def local_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def local_now() -> datetime:
    return datetime.now(local_timezone())
