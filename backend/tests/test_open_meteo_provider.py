from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.open_meteo.provider import OpenMeteoProvider, _build_advice, _wmo_description


def _daily_payload(**overrides) -> dict:
    payload = {
        "temperature_2m_max": [22.5],
        "temperature_2m_min": [15.0],
        "apparent_temperature_max": [21.0],
        "precipitation_probability_max": [30],
        "windspeed_10m_max": [18.5],
        "weathercode": [2],
    }
    payload.update(overrides)
    return payload


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


class TestGetDailyForecast:
    @pytest.fixture
    def client(self):
        return AsyncMock()

    @pytest.fixture
    def provider(self, client):
        return OpenMeteoProvider(client)

    @pytest.mark.asyncio
    async def test_returns_weather_forecast(self, provider, client):
        client.fetch_daily.return_value = _daily_payload()
        result = await provider.get_daily_forecast(date(2026, 6, 23))

        assert result.temperature_max_c == 22.5
        assert result.temperature_min_c == 15.0
        assert result.feels_like_max_c == 21.0
        assert result.precipitation_probability == 30
        assert result.wind_speed_max_kmh == 18.5
        assert result.description == "Partly cloudy"

    @pytest.mark.asyncio
    async def test_handles_null_precipitation(self, provider, client):
        client.fetch_daily.return_value = _daily_payload(precipitation_probability_max=[None])
        result = await provider.get_daily_forecast(date(2026, 6, 23))
        assert result.precipitation_probability == 0

    @pytest.mark.asyncio
    async def test_requests_porto_coordinates_and_date(self, provider, client):
        client.fetch_daily.return_value = _daily_payload()
        await provider.get_daily_forecast(date(2026, 6, 23))

        args, kwargs = client.fetch_daily.call_args
        assert args[0] == 41.1579
        assert args[1] == -8.6291
        assert args[3] == date(2026, 6, 23)

    @pytest.mark.asyncio
    async def test_logs_sync_call_on_success(self, provider, client):
        client.fetch_daily.return_value = _daily_payload()
        session = AsyncMock()
        with patch("app.integrations.open_meteo.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_daily_forecast(date(2026, 6, 23), session=session)

        mock_log.assert_awaited_once()
        assert mock_log.call_args.kwargs["provider"] == "open_meteo"
        assert mock_log.call_args.kwargs["status"] == "ok"

    @pytest.mark.asyncio
    async def test_skips_logging_when_session_none(self, provider, client):
        client.fetch_daily.return_value = _daily_payload()
        with patch("app.integrations.open_meteo.provider.create_sync_log", new=AsyncMock()) as mock_log:
            await provider.get_daily_forecast(date(2026, 6, 23))

        mock_log.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises_on_failure(self, provider, client):
        client.fetch_daily.side_effect = Exception("HTTP error")
        session = AsyncMock()
        with patch("app.integrations.open_meteo.provider.create_sync_log", new=AsyncMock()) as mock_log:
            with pytest.raises(Exception):
                await provider.get_daily_forecast(date(2026, 6, 23), session=session)

        assert mock_log.call_args.kwargs["status"] == "error"


class TestGetForecastForCity:
    @pytest.fixture
    def client(self):
        return AsyncMock()

    @pytest.fixture
    def provider(self, client):
        return OpenMeteoProvider(client)

    @pytest.mark.asyncio
    async def test_returns_forecast_and_label(self, provider, client):
        client.geocode.return_value = {
            "name": "Lisbon", "country_code": "PT", "latitude": 38.7, "longitude": -9.1, "timezone": "Europe/Lisbon",
        }
        client.fetch_daily.return_value = _daily_payload()

        forecast, label = await provider.get_forecast_for_city("Lisbon", date(2026, 6, 23))

        assert label == "Lisbon, PT"
        assert forecast.temperature_max_c == 22.5

    @pytest.mark.asyncio
    async def test_raises_when_city_not_found(self, provider, client):
        client.geocode.return_value = None
        with pytest.raises(ValueError):
            await provider.get_forecast_for_city("Nowhere", date(2026, 6, 23))
