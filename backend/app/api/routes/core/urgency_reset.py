from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import UrgencyResetServiceDep
from app.features.core.urgency_reset.schemas import UrgencyResetRead

router = APIRouter(prefix="/core/urgency-reset", tags=["core"], dependencies=[Depends(require_auth)])


@router.post("", response_model=UrgencyResetRead)
async def reset_urgency(
    service: UrgencyResetServiceDep,
    days: Annotated[int | None, Query(ge=1, le=365)] = None,
) -> UrgencyResetRead:
    return await service.reset(days)
