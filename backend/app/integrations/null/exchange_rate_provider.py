from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession


class NullExchangeRateProvider:
    """No-op ExchangeRateProvider: never has a rate.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so finance
    features run without a live Frankfurter API call. Callers already treat
    a missing rate as "conversion unavailable" for the real provider too
    (Frankfurter has no data for a given date/currency), so this is a
    legitimate response, not a special case.
    """

    async def get_rate(
        self,
        currency: str,
        on_date: date,
        session: AsyncSession | None = None,
    ) -> Decimal | None:
        return None
