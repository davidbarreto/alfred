from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.frankfurter.provider import FrankfurterProvider


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        "error", request=MagicMock(), response=MagicMock(status_code=status_code)
    )


def _make_provider() -> tuple[FrankfurterProvider, AsyncMock]:
    client = AsyncMock()
    return FrankfurterProvider(client), client


class TestGetRate:
    @pytest.mark.asyncio
    async def test_returns_rate_on_success(self):
        provider, client = _make_provider()
        client.get_historical_rate.return_value = {"rates": {"USD": 1.08}}

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()) as mock_log:
            session = AsyncMock()
            result = await provider.get_rate("USD", date(2026, 6, 1), session=session)

        assert result == Decimal("1.08")
        mock_log.assert_awaited_once()
        assert mock_log.call_args.kwargs["status"] == "ok"

    @pytest.mark.asyncio
    async def test_steps_back_on_404_until_rate_found(self):
        provider, client = _make_provider()
        client.get_historical_rate.side_effect = [
            _http_status_error(404),
            _http_status_error(404),
            {"rates": {"USD": 1.10}},
        ]

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()):
            result = await provider.get_rate("USD", date(2026, 6, 3))

        assert result == Decimal("1.10")
        assert client.get_historical_rate.await_count == 3

    @pytest.mark.asyncio
    async def test_lookback_exhausted_returns_none(self):
        provider, client = _make_provider()
        client.get_historical_rate.side_effect = _http_status_error(404)

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()) as mock_log:
            result = await provider.get_rate("USD", date(2026, 6, 10), session=AsyncMock())

        assert result is None
        assert mock_log.call_args.kwargs["status"] == "error"

    @pytest.mark.asyncio
    async def test_date_before_euro_epoch_skips_client_entirely(self):
        provider, client = _make_provider()

        result = await provider.get_rate("USD", date(1998, 1, 1))

        assert result is None
        client.get_historical_rate.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_404_http_error_returns_none(self):
        provider, client = _make_provider()
        client.get_historical_rate.side_effect = _http_status_error(500)

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()):
            result = await provider.get_rate("USD", date(2026, 6, 1))

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_currency_in_response_returns_none(self):
        provider, client = _make_provider()
        client.get_historical_rate.return_value = {"rates": {}}

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()):
            result = await provider.get_rate("USD", date(2026, 6, 1))

        assert result is None

    @pytest.mark.asyncio
    async def test_logging_skipped_when_session_none(self):
        provider, client = _make_provider()
        client.get_historical_rate.return_value = {"rates": {"USD": 1.08}}

        with patch("app.integrations.frankfurter.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_rate("USD", date(2026, 6, 1), session=None)

        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_logging_failure_is_swallowed(self):
        provider, client = _make_provider()
        client.get_historical_rate.return_value = {"rates": {"USD": 1.08}}

        with patch(
            "app.integrations.frankfurter.provider.create_sync_log",
            new=AsyncMock(side_effect=Exception("db down")),
        ):
            result = await provider.get_rate("USD", date(2026, 6, 1), session=AsyncMock())

        assert result == Decimal("1.08")
