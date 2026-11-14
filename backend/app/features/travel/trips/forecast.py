"""Weather for a trip's cities: the forecast when the trip is near, else last year's same dates. Pure helpers, no DB."""
import logging
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Open-Meteo forecasts reach 16 days; stay safely inside.
FORECAST_HORIZON_DAYS = 14
RAIN_MM = 2.0

# "actual": archive values of a finished trip; "mixed": a finished trip holding more than one kind of day.
ForecastMode = Literal["forecast", "climate", "actual", "mixed", "none"]


class ForecastDay(BaseModel):
    date: date
    min_c: float | None
    max_c: float | None
    precip_mm: float | None
    rain: bool


class CityForecast(BaseModel):
    city: str
    days: list[ForecastDay]


class TripForecast(BaseModel):
    trip_id: int
    mode: ForecastMode
    available: bool
    message: str | None = None
    # The trip is over: the saved snapshot is shown and Open-Meteo is no longer asked.
    finished: bool = False
    # When the newest day shown was fetched; older than today means the weather service could not be reached.
    as_of: date | None = None
    cities: list[CityForecast] = []


def pick_mode(start: date, today: date) -> ForecastMode:
    return "forecast" if start <= today + timedelta(days=FORECAST_HORIZON_DAYS) else "climate"


def a_year_earlier(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 Feb
        return day.replace(year=day.year - 1, day=28)


def days_from_daily(daily: dict[str, Any], dates: list[date]) -> list[ForecastDay]:
    """Open-Meteo's column-wise `daily` block as rows, labelled with the trip's own dates."""
    mins, maxs, rain = daily.get("temperature_2m_min") or [], daily.get("temperature_2m_max") or [], daily.get("precipitation_sum") or []

    def at(values: list, i: int):
        return values[i] if i < len(values) else None

    return [
        ForecastDay(
            date=day, min_c=at(mins, i), max_c=at(maxs, i), precip_mm=at(rain, i),
            rain=(at(rain, i) or 0) >= RAIN_MM,
        )
        for i, day in enumerate(dates)
    ]

