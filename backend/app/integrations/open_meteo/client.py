from __future__ import annotations

from datetime import date
from typing import Any

import httpx

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"


class OpenMeteoClient:
    """Thin async wrapper around the Open-Meteo REST APIs.

    Knows nothing about domain concepts (weather descriptions, advice) --
    only HTTP and Open-Meteo's wire format.
    """

    async def geocode(self, city: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                _GEOCODING_URL, params={"name": city, "count": 1, "language": "en"}
            )
            response.raise_for_status()
        results = response.json().get("results", [])
        return results[0] if results else None

    async def fetch_daily(self, lat: float, lon: float, timezone: str, for_date: date) -> dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,apparent_temperature_max,precipitation_probability_max,windspeed_10m_max,weathercode",
            "timezone": timezone,
            "start_date": for_date.isoformat(),
            "end_date": for_date.isoformat(),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
        return response.json()["daily"]
