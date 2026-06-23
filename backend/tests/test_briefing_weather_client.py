from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.features.briefing.weather_client import WeatherClient, _build_advice, _wmo_description


class TestWmoDescription:
    def test_known_code(self):
        assert _wmo_description(0) == "Clear sky"
        assert _wmo_description(61) == "Light rain"
        assert _wmo_description(95) == "Thunderstorm"

    def test_unknown_code_returns_fallback(self):
        assert _wmo_description(999) == "Weather code 999"


class TestBuildAdvice:
    def test_umbrella_when_rain_probability_high(self):
        advice = _build_advice(
            feels_like_max_c=20.0,
            temperature_min_c=15.0,
            precipitation_probability=40,
            wind_speed_max_kmh=10.0,
        )
        assert "Take an umbrella" in advice

    def test_no_umbrella_when_rain_probability_low(self):
        advice = _build_advice(
            feels_like_max_c=20.0,
            temperature_min_c=15.0,
            precipitation_probability=39,
            wind_speed_max_kmh=10.0,
        )
        assert "Take an umbrella" not in advice

    def test_coat_when_feels_like_cold(self):
        advice = _build_advice(
            feels_like_max_c=14.0,
            temperature_min_c=15.0,
            precipitation_probability=0,
            wind_speed_max_kmh=10.0,
        )
        assert "Take a coat" in advice

    def test_coat_when_min_temperature_low(self):
        advice = _build_advice(
            feels_like_max_c=20.0,
            temperature_min_c=11.0,
            precipitation_probability=0,
            wind_speed_max_kmh=10.0,
        )
        assert "Take a coat" in advice

    def test_no_coat_when_mild(self):
        advice = _build_advice(
            feels_like_max_c=20.0,
            temperature_min_c=15.0,
            precipitation_probability=0,
            wind_speed_max_kmh=10.0,
        )
        assert "Take a coat" not in advice

    def test_wind_warning_when_strong(self):
        advice = _build_advice(
            feels_like_max_c=20.0,
            temperature_min_c=15.0,
            precipitation_probability=0,
            wind_speed_max_kmh=41.0,
        )
        assert "Strong winds expected" in advice

    def test_empty_advice_on_good_day(self):
        advice = _build_advice(
            feels_like_max_c=22.0,
            temperature_min_c=18.0,
            precipitation_probability=10,
            wind_speed_max_kmh=15.0,
        )
        assert advice == []

    def test_multiple_pieces_of_advice(self):
        advice = _build_advice(
            feels_like_max_c=10.0,
            temperature_min_c=8.0,
            precipitation_probability=80,
            wind_speed_max_kmh=50.0,
        )
        assert len(advice) == 3


class TestWeatherClient:
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
    async def test_returns_weather_forecast(self, mock_response):
        client = WeatherClient()
        with patch("app.features.briefing.weather_client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await client.get_daily_forecast(date(2026, 6, 23))

        assert result.temperature_max_c == 22.5
        assert result.temperature_min_c == 15.0
        assert result.feels_like_max_c == 21.0
        assert result.precipitation_probability == 30
        assert result.wind_speed_max_kmh == 18.5
        assert result.description == "Partly cloudy"

    @pytest.mark.asyncio
    async def test_handles_null_precipitation(self, mock_response):
        mock_response.json.return_value["daily"]["precipitation_probability_max"] = [None]
        client = WeatherClient()
        with patch("app.features.briefing.weather_client.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            result = await client.get_daily_forecast(date(2026, 6, 23))

        assert result.precipitation_probability == 0

    @pytest.mark.asyncio
    async def test_requests_correct_params(self, mock_response):
        client = WeatherClient()
        with patch("app.features.briefing.weather_client.httpx.AsyncClient") as mock_http:
            get_mock = AsyncMock(return_value=mock_response)
            mock_http.return_value.__aenter__.return_value.get = get_mock
            await client.get_daily_forecast(date(2026, 6, 23))

        call_kwargs = get_mock.call_args
        params = call_kwargs[1]["params"]
        assert params["latitude"] == 41.1579
        assert params["longitude"] == -8.6291
        assert params["start_date"] == "2026-06-23"
        assert params["end_date"] == "2026-06-23"
