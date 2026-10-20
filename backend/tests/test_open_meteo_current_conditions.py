from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.null.weather_provider import NullWeatherProvider
from app.integrations.open_meteo.client import OpenMeteoClient
from app.integrations.open_meteo.provider import OpenMeteoProvider

_CURRENT = {"temperature_2m": 14.5, "precipitation": 0.2, "wind_speed_10m": 12.0, "weather_code": 61}


class TestFetchCurrent:
    async def test_requests_current_fields_for_the_given_point(self):
        response = MagicMock()
        response.json.return_value = {"current": _CURRENT}
        client = OpenMeteoClient()
        with patch("app.integrations.open_meteo.client.httpx.AsyncClient") as mock_http:
            request_mock = AsyncMock(return_value=response)
            mock_http.return_value.__aenter__.return_value.request = request_mock
            result = await client.fetch_current(38.7, -9.1)

        params = request_mock.call_args[1]["params"]
        assert (params["latitude"], params["longitude"]) == (38.7, -9.1)
        assert "weather_code" in params["current"] and "precipitation" in params["current"]
        assert result == _CURRENT


class TestGetCurrentConditions:
    async def test_maps_the_response_to_a_snapshot(self):
        client = AsyncMock()
        client.fetch_current.return_value = _CURRENT
        snapshot = await OpenMeteoProvider(client).get_current_conditions(38.7, -9.1)

        client.fetch_current.assert_awaited_once_with(38.7, -9.1)
        assert (snapshot.temp_c, snapshot.precipitation_mm, snapshot.wind_kmh, snapshot.weather_code) == (14.5, 0.2, 12.0, 61)

    async def test_defaults_to_porto_without_coordinates(self):
        client = AsyncMock()
        client.fetch_current.return_value = _CURRENT
        await OpenMeteoProvider(client).get_current_conditions()
        assert client.fetch_current.await_args.args == (41.1579, -8.6291)

    async def test_null_provider_returns_nothing(self):
        assert await NullWeatherProvider().get_current_conditions() is None
