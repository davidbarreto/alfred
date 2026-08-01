from datetime import date

import pytest

from app.integrations.null.exchange_rate_provider import NullExchangeRateProvider


class TestNullExchangeRateProvider:

    @pytest.mark.asyncio
    async def test_get_rate_always_returns_none(self):
        provider = NullExchangeRateProvider()

        rate = await provider.get_rate("USD", date(2026, 1, 1))

        assert rate is None
