from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import StudyTrackServiceDep
from app.features.study.tracks.schemas import StudyTrackRead

router = APIRouter(prefix="/study/tracks", tags=["study"], dependencies=[Depends(require_auth)])


@router.get("", response_model=list[StudyTrackRead])
async def list_tracks(service: StudyTrackServiceDep):
    return await service.get_tracks()
