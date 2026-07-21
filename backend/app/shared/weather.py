from __future__ import annotations

from datetime import date
from typing import Protocol

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
