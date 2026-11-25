from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ChatSettingsServiceDep
from app.features.core.chat_settings.schemas import ChatSettingsRead, ChatSettingsUpdate

router = APIRouter(prefix="/core/chat-settings", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=ChatSettingsRead)
async def get_chat_settings(service: ChatSettingsServiceDep) -> ChatSettingsRead:
    return await service.get()


@router.put("", response_model=ChatSettingsRead)
async def update_chat_settings(request: ChatSettingsUpdate, service: ChatSettingsServiceDep) -> ChatSettingsRead:
    return await service.update(request)
