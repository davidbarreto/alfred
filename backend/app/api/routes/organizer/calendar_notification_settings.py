from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import CalendarNotificationSettingsServiceDep
from app.features.organizer.calendar_events.notification_settings.schemas import (
    CalendarNotificationCascadeUpdate,
    CalendarNotificationCascadesRead,
)

router = APIRouter(
    prefix="/organizer/calendar-notification-settings", tags=["organizer"], dependencies=[Depends(require_auth)]
)


@router.get("", response_model=CalendarNotificationCascadesRead)
async def get_calendar_notification_settings(service: CalendarNotificationSettingsServiceDep):
    return await service.get()


@router.put("/{profile}", response_model=CalendarNotificationCascadesRead)
async def update_calendar_notification_profile(
    profile: str, request: CalendarNotificationCascadeUpdate, service: CalendarNotificationSettingsServiceDep
):
    return await service.update_profile(profile, request)
