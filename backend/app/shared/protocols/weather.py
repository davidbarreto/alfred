from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import WeatherForecast


class WeatherProvider(Protocol):
    """Async interface for daily weather forecasts at a point.

    Swap the implementation (Open-Meteo, OpenWeatherMap, …) without touching the briefing service layer. Where to look
    is the caller's: the weather place setting (`WeatherSettingsService.resolve`).
    """

    async def get_daily_forecast(
        self, for_date: date, lat: float, lon: float, session: AsyncSession | None = None
    ) -> WeatherForecast: ...

    async def geocode_city(self, name: str) -> tuple[float, float] | None:
        """(latitude, longitude) of a city found by name ("Lisbon, Portugal"), or None."""
        ...


class WeatherSnapshot(BaseModel):
    """Current conditions at a point in time, as stored in a metric entry's context."""

    temp_c: float
    precipitation_mm: float
    wind_kmh: float
    weather_code: int


class ConditionsProvider(Protocol):
    """Current conditions at a point."""

    async def get_current_conditions(self, lat: float, lon: float) -> WeatherSnapshot | None: ...

    async def geocode_city(self, name: str) -> tuple[float, float] | None: ...
