from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import CatchupServiceDep
from app.features.core.catchup.schemas import CatchupApply, CatchupApplyRead, CatchupRead

router = APIRouter(prefix="/core/catchup", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("", response_model=CatchupRead)
async def get_catchup(service: CatchupServiceDep) -> CatchupRead:
    return await service.get_suggestions()


@router.post("/apply", response_model=CatchupApplyRead)
async def apply_catchup(request: CatchupApply, service: CatchupServiceDep) -> CatchupApplyRead:
    return await service.apply(request)
