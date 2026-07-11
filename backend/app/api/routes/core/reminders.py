from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import ReminderServiceDep
from app.features.core.reminders.schemas import ReminderDigest

router = APIRouter(prefix="/core/reminders", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/due", response_model=ReminderDigest)
async def get_due_reminders(service: ReminderServiceDep) -> ReminderDigest:
    return await service.build_due_digest()
