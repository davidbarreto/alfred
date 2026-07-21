from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.exchange_rates.tables import ExchangeRate


class ExchangeRateRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_rate(self, rate_date: date, currency: str) -> ExchangeRate | None:
        result = await self._session.execute(
            select(ExchangeRate).where(
                ExchangeRate.rate_date == rate_date, ExchangeRate.currency == currency
            )
        )
        return result.scalars().first()

    async def create_rate(self, rate_date: date, currency: str, rate: Decimal) -> ExchangeRate:
        exchange_rate = ExchangeRate(rate_date=rate_date, currency=currency, rate=rate)
        self._session.add(exchange_rate)
        await self._session.commit()
        await self._session.refresh(exchange_rate)
        return exchange_rate
