from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.open_meteo.client import OpenMeteoClient


class TestFetchDaily:
    @pytest.fixture
    def mock_response(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "daily": {
                "time": ["2026-06-23"],
                "temperature_2m_max": [22.5],
                "temperature_2m_min": [15.0],
                "apparent_temperature_max": [21.0],
                "precipitation_probability_max": [30],
                "windspeed_10m_max": [18.5],
                "weathercode": [2],
            }
        }
        return response

    @pytest.mark.asyncio
    async def test_returns_daily_block(self, mock_response):
        client = OpenMeteoClient()
        with patch("app.integrations.open_meteo.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await client.fetch_daily(41.1579, -8.6291, "Europe/Lisbon", date(2026, 6, 23))

        assert result["temperature_2m_max"] == [22.5]

    @pytest.mark.asyncio
    async def test_requests_correct_params(self, mock_response):
        client = OpenMeteoClient()
        with patch("app.integrations.open_meteo.client.httpx.AsyncClient") as mock_http:
            get_mock = AsyncMock(return_value=mock_response)
            mock_http.return_value.__aenter__.return_value.get = get_mock
            await client.fetch_daily(41.1579, -8.6291, "Europe/Lisbon", date(2026, 6, 23))

        params = get_mock.call_args[1]["params"]
        assert params["latitude"] == 41.1579
        assert params["longitude"] == -8.6291
        assert params["start_date"] == "2026-06-23"
        assert params["end_date"] == "2026-06-23"


class TestGeocode:
    @pytest.mark.asyncio
    async def test_returns_first_result(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"results": [{"name": "Lisbon", "country_code": "PT"}]}

        client = OpenMeteoClient()
        with patch("app.integrations.open_meteo.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            result = await client.geocode("Lisbon")

        assert result == {"name": "Lisbon", "country_code": "PT"}

    @pytest.mark.asyncio
    async def test_returns_none_when_no_results(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {"results": []}

        client = OpenMeteoClient()
        with patch("app.integrations.open_meteo.client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
            result = await client.geocode("Nowhere")

        assert result is None
