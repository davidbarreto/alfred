from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ReminderSettingsServiceDep
from app.features.core.reminders.schemas import ReminderSettingsRead, ReminderSettingsUpdate

router = APIRouter(prefix="/core/reminder-settings", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=ReminderSettingsRead)
async def get_reminder_settings(service: ReminderSettingsServiceDep) -> ReminderSettingsRead:
    return await service.get()


@router.put("", response_model=ReminderSettingsRead)
async def update_reminder_settings(
    request: ReminderSettingsUpdate, service: ReminderSettingsServiceDep
) -> ReminderSettingsRead:
    return await service.update(request)
