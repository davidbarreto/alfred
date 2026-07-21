import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from app.features.finance.exchange_rates.service import ExchangeRateService


@pytest.fixture
def service():
    svc = ExchangeRateService.__new__(ExchangeRateService)
    svc._session = AsyncMock()
    svc._repo = AsyncMock()
    svc._provider = AsyncMock()
    return svc


class TestGetOrFetchRate:
    async def test_eur_short_circuits_without_io(self, service):
        result = await service.get_or_fetch_rate(date(2026, 6, 1), "EUR")
        assert result == Decimal("1")
        service._repo.get_rate.assert_not_called()
        service._provider.get_rate.assert_not_called()

    async def test_cache_hit_skips_provider(self, service):
        cached = MagicMock(rate=Decimal("1.08"))
        service._repo.get_rate.return_value = cached

        result = await service.get_or_fetch_rate(date(2026, 6, 1), "USD")

        assert result == Decimal("1.08")
        service._provider.get_rate.assert_not_called()

    async def test_cache_miss_fetches_and_persists(self, service):
        service._repo.get_rate.return_value = None
        service._provider.get_rate.return_value = Decimal("1.08")

        result = await service.get_or_fetch_rate(date(2026, 6, 1), "USD")

        assert result == Decimal("1.08")
        service._provider.get_rate.assert_awaited_once_with(
            "USD", date(2026, 6, 1), session=service._session
        )
        service._repo.create_rate.assert_awaited_once_with(date(2026, 6, 1), "USD", Decimal("1.08"))

    async def test_provider_failure_returns_none(self, service):
        service._repo.get_rate.return_value = None
        service._provider.get_rate.return_value = None

        result = await service.get_or_fetch_rate(date(2026, 6, 1), "XXX")

        assert result is None
        service._repo.create_rate.assert_not_called()

    async def test_concurrent_cache_write_race_is_swallowed(self, service):
        service._repo.get_rate.return_value = None
        service._provider.get_rate.return_value = Decimal("1.08")
        service._repo.create_rate.side_effect = IntegrityError("stmt", {}, Exception("dup"))

        result = await service.get_or_fetch_rate(date(2026, 6, 1), "USD")

        assert result == Decimal("1.08")
        service._session.rollback.assert_awaited_once()

    async def test_normalizes_currency_case(self, service):
        service._repo.get_rate.return_value = None
        service._provider.get_rate.return_value = Decimal("1.08")

        await service.get_or_fetch_rate(date(2026, 6, 1), "usd")

        service._provider.get_rate.assert_awaited_once_with(
            "USD", date(2026, 6, 1), session=service._session
        )


class TestConvertToEur:
    async def test_converts_using_rate(self, service):
        service._repo.get_rate.return_value = MagicMock(rate=Decimal("2"))

        result = await service.convert_to_eur(Decimal("100.00"), "USD", date(2026, 6, 1))

        assert result == Decimal("50.00")

    async def test_returns_none_when_rate_unavailable(self, service):
        service._repo.get_rate.return_value = None
        service._provider.get_rate.return_value = None

        result = await service.convert_to_eur(Decimal("100.00"), "XXX", date(2026, 6, 1))

        assert result is None

    async def test_eur_amount_unchanged(self, service):
        result = await service.convert_to_eur(Decimal("100.00"), "EUR", date(2026, 6, 1))
        assert result == Decimal("100.00")
