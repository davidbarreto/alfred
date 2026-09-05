from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import InterviewPreferencesServiceDep
from app.features.organizer.interviews.preferences.schemas import (
    InterviewPreferencesRead,
    InterviewPreferencesUpdate,
)

router = APIRouter(
    prefix="/organizer/interview-preferences",
    tags=["organizer"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=InterviewPreferencesRead)
async def get_preferences(service: InterviewPreferencesServiceDep) -> InterviewPreferencesRead:
    return await service.get_preferences()


@router.patch("", response_model=InterviewPreferencesRead)
async def update_preferences(
    request: InterviewPreferencesUpdate, service: InterviewPreferencesServiceDep
) -> InterviewPreferencesRead:
    return await service.update_preferences(request)
