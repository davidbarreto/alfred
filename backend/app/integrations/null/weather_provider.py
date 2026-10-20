from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import WeatherForecast
from app.shared.weather import WeatherSnapshot


class NullWeatherProvider:
    """No-op WeatherProvider: returns a canned forecast without calling Open-Meteo.

    Used when DISABLE_INTEGRATIONS is set (CI smoke tests) so briefing
    generation runs end-to-end deterministically.
    """

    async def get_daily_forecast(
        self, for_date: date, session: AsyncSession | None = None
    ) -> WeatherForecast:
        return WeatherForecast(
            temperature_max_c=0.0,
            temperature_min_c=0.0,
            feels_like_max_c=0.0,
            precipitation_probability=0,
            wind_speed_max_kmh=0.0,
            description="unavailable — integrations disabled",
            advice=[],
        )

    async def get_current_conditions(
        self, lat: float | None = None, lon: float | None = None
    ) -> WeatherSnapshot | None:
        return None
