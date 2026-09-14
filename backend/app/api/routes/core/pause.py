from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import GlobalPauseServiceDep
from app.features.core.pause.schemas import PauseLogRead, PauseResumeRead, PauseStateRead

router = APIRouter(prefix="/core/pause", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=PauseStateRead)
async def get_pause_state(service: GlobalPauseServiceDep) -> PauseStateRead:
    return await service.get_state()


@router.get("/history", response_model=list[PauseLogRead])
async def get_pause_history(
    service: GlobalPauseServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PauseLogRead]:
    return await service.list_history(limit=limit)


@router.post("", response_model=PauseStateRead)
async def pause(service: GlobalPauseServiceDep) -> PauseStateRead:
    return await service.pause()


@router.post("/resume", response_model=PauseResumeRead)
async def resume(service: GlobalPauseServiceDep) -> PauseResumeRead:
    return await service.resume()
