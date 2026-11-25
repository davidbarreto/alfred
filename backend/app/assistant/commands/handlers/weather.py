import logging
from datetime import date
from typing import Any

from fastapi import HTTPException, status

from app.features.core.weather_settings.schemas import NO_PLACE_HINT
from app.features.core.weather_settings.service import WeatherSettingsService
from app.integrations.open_meteo.client import OpenMeteoClient
from app.integrations.open_meteo.provider import OpenMeteoProvider
from app.shared.utils.timezone import local_today

logger = logging.getLogger(__name__)

_client = OpenMeteoProvider(OpenMeteoClient())


async def handle_weather(
    command: str, arguments: dict[str, Any], weather_places: WeatherSettingsService | None = None
) -> Any:
    logger.debug("handle_weather: command=%s args_keys=%s", command, list(arguments.keys()))

    if command != "current":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown weather command: {command}")

    extracted = str(arguments.get("location", "")).strip()
    date_arg = arguments.get("date")
    try:
        forecast_date = date.fromisoformat(date_arg) if date_arg else local_today()
    except ValueError:
        forecast_date = local_today()

    if extracted:
        try:
            forecast, resolved_location = await _client.get_forecast_for_city(extracted, forecast_date)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    else:
        # No place in the message: the weather place setting (Home by default).
        place = await weather_places.resolve(_client.geocode_city) if weather_places is not None else None
        if place is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Which place? {NO_PLACE_HINT}")
        logger.debug("handle_weather: no place given, using the weather place: source=%s", place.source)
        forecast = await _client.get_forecast_at(place.latitude, place.longitude, forecast_date)
        resolved_location = place.label

    return {
        "location": resolved_location,
        "date": forecast_date.isoformat(),
        "location_inferred": not extracted,
        **forecast.model_dump(mode='json'),
    }
