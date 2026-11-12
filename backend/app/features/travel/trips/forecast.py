"""Weather for a trip's stay cities: the forecast when the trip is near, else last year's same dates. No DB."""
import logging
import time as _time
from datetime import date, timedelta
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Open-Meteo forecasts reach 16 days; stay safely inside.
FORECAST_HORIZON_DAYS = 14
RAIN_MM = 2.0
_CACHE_TTL_SECONDS = 3600

ForecastMode = Literal["forecast", "climate", "none"]


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
    cities: list[CityForecast] = []


def pick_mode(start: date, end: date, today: date) -> ForecastMode:
    if end < today:
        return "none"
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


_cache: dict[tuple, tuple[float, list[ForecastDay]]] = {}


async def cached(key: tuple, load: Callable[[], Awaitable[list[ForecastDay]]]) -> list[ForecastDay]:
    hit = _cache.get(key)
    if hit and _time.monotonic() - hit[0] < _CACHE_TTL_SECONDS:
        return hit[1]
    value = await load()
    _cache[key] = (_time.monotonic(), value)
    return value
