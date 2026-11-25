from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import CsSettingsServiceDep
from app.features.cs.settings.schemas import CsSettingsRead, CsSettingsUpdate

router = APIRouter(prefix="/cs/settings", tags=["cs"], dependencies=[Depends(require_auth)])


@router.get("", response_model=CsSettingsRead)
async def get_cs_settings(service: CsSettingsServiceDep) -> CsSettingsRead:
    return await service.get()


@router.put("", response_model=CsSettingsRead)
async def update_cs_settings(request: CsSettingsUpdate, service: CsSettingsServiceDep) -> CsSettingsRead:
    return await service.update(request)
