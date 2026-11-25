from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import LanguageSettingsServiceDep
from app.features.language.settings_schemas import LanguageSettingsRead, LanguageSettingsUpdate

router = APIRouter(prefix="/language/settings", tags=["language"], dependencies=[Depends(require_auth)])


@router.get("", response_model=LanguageSettingsRead)
async def get_language_settings(service: LanguageSettingsServiceDep) -> LanguageSettingsRead:
    return await service.get()


@router.put("", response_model=LanguageSettingsRead)
async def update_language_settings(
    request: LanguageSettingsUpdate, service: LanguageSettingsServiceDep
) -> LanguageSettingsRead:
    return await service.update(request)
