from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ContactBirthdayNotificationServiceDep
from app.features.core.reminders.schemas import ReminderDigest

router = APIRouter(
    prefix="/organizer/contact-birthday-notifications", tags=["organizer"], dependencies=[Depends(require_auth)]
)


@router.get("/due", response_model=ReminderDigest)
async def get_due_contact_birthday_notifications(service: ContactBirthdayNotificationServiceDep) -> ReminderDigest:
    return await service.build_due_digest()
