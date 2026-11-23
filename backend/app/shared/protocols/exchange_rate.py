from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession


class ExchangeRateProvider(Protocol):
    """Async interface for historical foreign-exchange rate lookups.

    Swap the implementation (Frankfurter, a paid provider, …) without touching
    the finance exchange-rate caching service.
    """

    async def get_rate(
        self,
        currency: str,
        on_date: date,
        session: AsyncSession | None = None,
    ) -> Decimal | None: ...
