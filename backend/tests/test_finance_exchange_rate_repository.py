import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.exchange_rates.repository import ExchangeRateRepository


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    return r


class TestGetRate:
    async def test_found(self):
        session = _make_session()
        rate = MagicMock()
        session.execute.return_value = _scalar_first(rate)
        result = await ExchangeRateRepository(session).get_rate(date(2026, 6, 1), "USD")
        assert result == rate

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await ExchangeRateRepository(session).get_rate(date(2026, 6, 1), "USD")
        assert result is None


class TestCreateRate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        result = await ExchangeRateRepository(session).create_rate(
            date(2026, 6, 1), "USD", Decimal("1.08")
        )
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert result.currency == "USD"
        assert result.rate == Decimal("1.08")
