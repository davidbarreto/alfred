from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import HolidayItem


class NullHolidayProvider:
    """No-op HolidayProvider: always reports no upcoming holidays.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so briefing
    generation doesn't need a real GCP_API_KEY.
    """

    async def get_holidays(
        self, from_date: date, to_date: date, session: AsyncSession | None = None
    ) -> list[HolidayItem]:
        return []
