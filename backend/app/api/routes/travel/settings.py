from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import TravelSettingsServiceDep
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate

router = APIRouter(prefix="/travel/settings", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=TravelSettingsRead)
async def get_travel_settings(service: TravelSettingsServiceDep) -> TravelSettingsRead:
    return await service.get()


@router.put("", response_model=TravelSettingsRead)
async def update_travel_settings(request: TravelSettingsUpdate, service: TravelSettingsServiceDep) -> TravelSettingsRead:
    return await service.update(request)
