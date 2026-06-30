import logging
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.features.briefing.weather_client import WeatherClient

logger = logging.getLogger(__name__)

_client = WeatherClient()


async def handle_weather(command: str, arguments: dict[str, Any]) -> Any:
    logger.debug("handle_weather: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "current":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown weather command: {command}")

    location = str(arguments.get("location", "")).strip() or "Porto"
    date_arg = arguments.get("date")
    try:
        forecast_date = date.fromisoformat(date_arg) if date_arg else date.today()
    except ValueError:
        forecast_date = date.today()

    try:
        forecast, resolved_location = await _client.get_forecast_for_city(location, forecast_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return {
        "location": resolved_location,
        "date": forecast_date.isoformat(),
        **forecast.model_dump(),
    }
