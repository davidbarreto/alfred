from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.exchange_rates.repository import ExchangeRateRepository
from app.shared.exchange_rate import ExchangeRateProvider

logger = logging.getLogger(__name__)


class ExchangeRateService:

    def __init__(self, session: AsyncSession, provider: ExchangeRateProvider) -> None:
        self._session = session
        self._repo = ExchangeRateRepository(session)
        self._provider = provider

    async def get_or_fetch_rate(self, rate_date: date, currency: str) -> Decimal | None:
        currency = currency.strip().upper()
        if currency == "EUR":
            return Decimal("1")

        cached = await self._repo.get_rate(rate_date, currency)
        if cached is not None:
            return cached.rate

        rate = await self._provider.get_rate(currency, rate_date, session=self._session)
        if rate is None:
            return None

        try:
            await self._repo.create_rate(rate_date, currency, rate)
        except IntegrityError:
            # A concurrent caller already cached this (rate_date, currency) pair.
            await self._session.rollback()

        logger.info("Exchange rate cached: date=%s currency=%s", rate_date, currency)
        return rate

    async def convert_to_eur(
        self, amount: Decimal, currency: str, on_date: date
    ) -> Decimal | None:
        rate = await self.get_or_fetch_rate(on_date, currency)
        if rate is None:
            return None
        return (amount / rate).quantize(Decimal("0.01"))
