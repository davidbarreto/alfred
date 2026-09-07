from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import GlobalPauseServiceDep
from app.features.core.pause.schemas import PauseResumeRead, PauseStateRead

router = APIRouter(prefix="/core/pause", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=PauseStateRead)
async def get_pause_state(service: GlobalPauseServiceDep) -> PauseStateRead:
    return await service.get_state()


@router.post("", response_model=PauseStateRead)
async def pause(service: GlobalPauseServiceDep) -> PauseStateRead:
    return await service.pause()


@router.post("/resume", response_model=PauseResumeRead)
async def resume(service: GlobalPauseServiceDep) -> PauseResumeRead:
    return await service.resume()
