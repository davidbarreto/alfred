from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import WeatherForecast


class WeatherProvider(Protocol):
    """Async interface for daily weather forecasts.

    Swap the implementation (Open-Meteo, OpenWeatherMap, …) without
    touching the briefing service layer.
    """

    async def get_daily_forecast(
        self, for_date: date, session: AsyncSession | None = None
    ) -> WeatherForecast: ...


class WeatherSnapshot(BaseModel):
    """Current conditions at a point in time, as stored in a metric entry's context."""

    temp_c: float
    precipitation_mm: float
    wind_kmh: float
    weather_code: int


class ConditionsProvider(Protocol):
    """Current conditions for a location; coordinates default to the provider's home location."""

    async def get_current_conditions(
        self, lat: float | None = None, lon: float | None = None
    ) -> WeatherSnapshot | None: ...
