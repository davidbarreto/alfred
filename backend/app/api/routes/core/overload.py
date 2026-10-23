from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import OverloadServiceDep
from app.features.core.overload.schemas import OverloadDayRead, OverloadStatusRead

router = APIRouter(prefix="/core/overload", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/status", response_model=OverloadStatusRead)
async def get_overload_status(service: OverloadServiceDep) -> OverloadStatusRead:
    return await service.status()


@router.get("/history", response_model=list[OverloadDayRead])
async def get_overload_history(
    service: OverloadServiceDep,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[OverloadDayRead]:
    return await service.history(days)
