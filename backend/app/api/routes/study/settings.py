from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import StudySettingsServiceDep
from app.features.study.settings.schemas import StudySettingsRead, StudySettingsUpdate

router = APIRouter(prefix="/study/settings", tags=["study"], dependencies=[Depends(require_auth)])


@router.get("", response_model=StudySettingsRead)
async def get_study_settings(service: StudySettingsServiceDep):
    return await service.get()


@router.put("", response_model=StudySettingsRead)
async def update_study_settings(request: StudySettingsUpdate, service: StudySettingsServiceDep):
    return await service.update(request)
