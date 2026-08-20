from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import CalendarNotificationServiceDep
from app.features.core.reminders.schemas import ReminderDigest

router = APIRouter(prefix="/organizer/calendar-notifications", tags=["organizer"], dependencies=[Depends(require_auth)])


@router.get("/due", response_model=ReminderDigest)
async def get_due_calendar_notifications(service: CalendarNotificationServiceDep) -> ReminderDigest:
    return await service.build_due_digest()
