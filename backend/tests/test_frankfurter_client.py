from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.frankfurter.client import FrankfurterClient


class TestGetHistoricalRate:
    @pytest.mark.asyncio
    async def test_returns_parsed_json(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"base": "EUR", "date": "2026-06-01", "rates": {"USD": 1.08}}

        client = FrankfurterClient()
        with patch("app.integrations.frankfurter.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            result = await client.get_historical_rate(date(2026, 6, 1), "USD")

        assert result["rates"]["USD"] == 1.08

    @pytest.mark.asyncio
    async def test_requests_correct_url_and_params(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"rates": {"USD": 1.08}}

        client = FrankfurterClient()
        with patch("app.integrations.frankfurter.client.httpx.AsyncClient") as mock_http:
            get_mock = AsyncMock(return_value=response)
            mock_http.return_value.__aenter__.return_value.get = get_mock
            await client.get_historical_rate(date(2026, 6, 1), "USD")

        args, kwargs = get_mock.call_args
        assert args[0] == "https://api.frankfurter.dev/v1/2026-06-01"
        assert kwargs["params"] == {"from": "EUR", "to": "USD"}

    @pytest.mark.asyncio
    async def test_raises_on_http_error(self):
        response = MagicMock()
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )

        client = FrankfurterClient()
        with patch("app.integrations.frankfurter.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            with pytest.raises(httpx.HTTPStatusError):
                await client.get_historical_rate(date(2026, 6, 1), "USD")
