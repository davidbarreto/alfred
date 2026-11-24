import logging
from datetime import date

from app.features.organizer.holidays.errors import HolidayRangeError
from app.features.organizer.holidays.schemas import HolidayRead
from app.shared.protocols.holiday import HolidayProvider

logger = logging.getLogger(__name__)

# A calendar month view padded by a week on each side fits easily; a whole year still does.
MAX_RANGE_DAYS = 366


class HolidayService:
    """Public holidays of the primary calendar (the first of HOLIDAY_CALENDARS) for the calendar views."""

    def __init__(self, provider: HolidayProvider | None) -> None:
        # None when no GCP_API_KEY is set: there are then no holidays to show.
        self._provider = provider

    async def list(self, start: date, end: date) -> list[HolidayRead]:
        if end < start:
            raise HolidayRangeError("'to' must not be before 'from'")
        if (end - start).days + 1 > MAX_RANGE_DAYS:
            raise HolidayRangeError(f"The range can cover at most {MAX_RANGE_DAYS} days")
        if self._provider is None:
            return []
        # No session: a read-only lookup made on every calendar page view, so the provider call is not logged.
        found = await self._provider.get_holidays(start, end)
        logger.debug("Holidays read: from=%s to=%s count=%d", start, end, len(found))
        return sorted(
            (HolidayRead(date=h.date, name=h.name, country=h.country) for h in found if start <= h.date <= end),
            key=lambda h: (h.date, h.name),
        )
