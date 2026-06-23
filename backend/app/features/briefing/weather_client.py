from __future__ import annotations

import logging
from datetime import date

import httpx

from app.features.briefing.schemas import WeatherForecast

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_PORTO_LAT = 41.1579
_PORTO_LON = -8.6291
_TIMEZONE = "Europe/Lisbon"

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


class WeatherClient:
    async def get_daily_forecast(self, for_date: date) -> WeatherForecast:
        params = {
            "latitude": _PORTO_LAT,
            "longitude": _PORTO_LON,
            "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,precipitation_probability_max,windspeed_10m_max,weathercode",
            "timezone": _TIMEZONE,
            "start_date": for_date.isoformat(),
            "end_date": for_date.isoformat(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()

        data = response.json()["daily"]
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
