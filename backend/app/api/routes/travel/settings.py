from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import TravelSettingsServiceDep
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate

router = APIRouter(prefix="/travel/settings", tags=["travel"], dependencies=[Depends(require_auth)])


@router.get("", response_model=TravelSettingsRead)
async def get_travel_settings(service: TravelSettingsServiceDep) -> TravelSettingsRead:
    return await service.get()


@router.put("", response_model=TravelSettingsRead)
async def update_travel_settings(request: TravelSettingsUpdate, service: TravelSettingsServiceDep) -> TravelSettingsRead:
    try:
        return await service.update(request)
    except TravelNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
