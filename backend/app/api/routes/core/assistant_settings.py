from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import AssistantSettingsServiceDep
from app.features.core.assistant_settings.schemas import AssistantSettingsRead, AssistantSettingsUpdate

router = APIRouter(prefix="/core/assistant-settings", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=AssistantSettingsRead)
async def get_assistant_settings(service: AssistantSettingsServiceDep) -> AssistantSettingsRead:
    return await service.get()


@router.put("", response_model=AssistantSettingsRead)
async def update_assistant_settings(
    request: AssistantSettingsUpdate, service: AssistantSettingsServiceDep
) -> AssistantSettingsRead:
    return await service.update(request)
