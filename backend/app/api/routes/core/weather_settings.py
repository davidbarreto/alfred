from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import WeatherSettingsServiceDep
from app.features.core.weather_settings.schemas import WeatherSettingsRead, WeatherSettingsUpdate

router = APIRouter(prefix="/core/weather-settings", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=WeatherSettingsRead)
async def get_weather_settings(service: WeatherSettingsServiceDep) -> WeatherSettingsRead:
    return await service.get()


@router.put("", response_model=WeatherSettingsRead)
async def update_weather_settings(
    request: WeatherSettingsUpdate, service: WeatherSettingsServiceDep
) -> WeatherSettingsRead:
    return await service.update(request)
