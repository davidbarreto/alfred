from datetime import datetime, timezone as dt_timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator

from app.shared.timezone import local_timezone


class LocalDateTime(TypeDecorator):
    """Stores a true UTC instant; presents a naive datetime in the app's
    currently configured local timezone to Python code. Insulates stored
    data from future changes to Settings.timezone — old and new rows always
    reproject correctly to whatever zone is configured at read time.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=local_timezone())
        return value.astimezone(dt_timezone.utc)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.astimezone(local_timezone()).replace(tzinfo=None)
