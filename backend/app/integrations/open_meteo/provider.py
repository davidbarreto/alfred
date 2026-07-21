from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.features.briefing.schemas import WeatherForecast
from app.integrations.provider_calls.repository import create_sync_log

from .client import OpenMeteoClient

logger = logging.getLogger(__name__)

_PORTO_LAT = 41.1579
_PORTO_LON = -8.6291

_WMO_DESCRIPTIONS: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Heavy drizzle",
    61: "Light rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Light snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Moderate rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}


def _wmo_description(code: int) -> str:
    return _WMO_DESCRIPTIONS.get(code, f"Weather code {code}")


def _build_advice(
    feels_like_max_c: float,
    temperature_min_c: float,
    precipitation_probability: int,
    wind_speed_max_kmh: float,
) -> list[str]:
    advice = []
    if precipitation_probability >= 40:
        advice.append("Take an umbrella")
    if feels_like_max_c < 15 or temperature_min_c < 12:
        advice.append("Take a coat")
    if wind_speed_max_kmh > 40:
        advice.append("Strong winds expected")
    return advice


class OpenMeteoProvider:
    def __init__(self, client: OpenMeteoClient) -> None:
        self._client = client

    async def get_forecast_for_city(self, city: str, for_date: date) -> tuple[WeatherForecast, str]:
        """Geocode a city name and return its forecast alongside the resolved city name."""
        result = await self._client.geocode(city)
        if result is None:
            raise ValueError(f"Location not found: {city!r}")
        resolved_name = result.get("name", city)
        country = result.get("country_code", "")
        label = f"{resolved_name}, {country}" if country else resolved_name
        logger.debug(
            "Geocoded %r → lat=%s lon=%s tz=%s", city, result["latitude"], result["longitude"], result.get("timezone")
        )
        data = await self._client.fetch_daily(
            result["latitude"], result["longitude"], result.get("timezone", "UTC"), for_date
        )
        return self._build_forecast(data), label

    async def get_daily_forecast(
        self, for_date: date, session: AsyncSession | None = None
    ) -> WeatherForecast:
        error: str | None = None
        forecast: WeatherForecast | None = None
        try:
            data = await self._client.fetch_daily(_PORTO_LAT, _PORTO_LON, get_settings().timezone, for_date)
            forecast = self._build_forecast(data)
        except Exception as exc:
            error = str(exc)
            await self._write_log(session, for_date, None, error)
            raise
        await self._write_log(session, for_date, forecast, None)
        return forecast

    def _build_forecast(self, data: dict) -> WeatherForecast:
        temp_max: float = data["temperature_2m_max"][0]
        temp_min: float = data["temperature_2m_min"][0]
        feels_like_max: float = data["apparent_temperature_max"][0]
        precip_prob: int = int(data["precipitation_probability_max"][0] or 0)
        wind_max: float = data["windspeed_10m_max"][0]
        code: int = data["weathercode"][0]

        return WeatherForecast(
            temperature_max_c=temp_max,
            temperature_min_c=temp_min,
            feels_like_max_c=feels_like_max,
            precipitation_probability=precip_prob,
            wind_speed_max_kmh=wind_max,
            description=_wmo_description(code),
            advice=_build_advice(feels_like_max, temp_min, precip_prob, wind_max),
        )

    async def _write_log(
        self,
        session: AsyncSession | None,
        for_date: date,
        forecast: WeatherForecast | None,
        error: str | None,
    ) -> None:
        if session is None:
            return
        try:
            await create_sync_log(
                session,
                provider="open_meteo",
                operation="get_daily_forecast",
                entity_type="weather_forecast",
                provider_entity_id=for_date.isoformat(),
                status="error" if error else "ok",
                request_payload={"date": for_date.isoformat()},
                response_payload=forecast.model_dump(mode="json") if forecast else None,
                error=error,
            )
        except Exception:
            logger.warning("Failed to write integration sync log", exc_info=True)
