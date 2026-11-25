from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.weather import handle_weather
from app.features.briefing.schemas import WeatherForecast
from app.features.core.weather_settings.schemas import WeatherPlace

_FORECAST = WeatherForecast(
    temperature_max_c=20, temperature_min_c=12, feels_like_max_c=19, precipitation_probability=10,
    wind_speed_max_kmh=8, description="Clear sky", advice=[],
)


@pytest.fixture
def client():
    with patch("app.assistant.commands.handlers.weather._client") as client:
        client.get_forecast_for_city = AsyncMock(return_value=(_FORECAST, "Lisbon, PT"))
        client.get_forecast_at = AsyncMock(return_value=_FORECAST)
        yield client


class TestHandleWeather:
    async def test_a_named_place_is_looked_up_by_name(self, client):
        result = await handle_weather("current", {"location": "Lisbon", "date": "2026-12-01"})

        client.get_forecast_for_city.assert_awaited_once_with("Lisbon", date(2026, 12, 1))
        assert (result["location"], result["location_inferred"]) == ("Lisbon, PT", False)

    async def test_without_a_place_the_weather_place_is_used(self, client):
        places = AsyncMock()
        places.resolve.return_value = WeatherPlace(source="home", label="Home", latitude=38.7, longitude=-9.1)

        result = await handle_weather("current", {"date": "2026-12-01"}, places)

        client.get_forecast_at.assert_awaited_once_with(38.7, -9.1, date(2026, 12, 1))
        assert (result["location"], result["location_inferred"]) == ("Home", True)

    async def test_without_any_place_it_says_how_to_set_one(self, client):
        places = AsyncMock()
        places.resolve.return_value = None

        with pytest.raises(HTTPException) as exc:
            await handle_weather("current", {}, places)

        assert exc.value.status_code == 404 and "Home location" in exc.value.detail
        client.get_forecast_at.assert_not_awaited()

    async def test_unknown_command(self, client):
        with pytest.raises(HTTPException):
            await handle_weather("tomorrow", {})
