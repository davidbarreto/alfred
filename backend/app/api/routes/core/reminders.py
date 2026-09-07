from datetime import date

from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import GlobalPauseServiceDep, ReminderServiceDep
from app.features.core.reminders.schemas import ReminderDigest

router = APIRouter(prefix="/core/reminders", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/due", response_model=ReminderDigest)
async def get_due_reminders(service: ReminderServiceDep, pause_service: GlobalPauseServiceDep) -> ReminderDigest:
    if await pause_service.is_paused():
        return ReminderDigest(date=date.today(), has_content=False, text="")
    return await service.build_due_digest()
