from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import ApiRequestServiceDep
from app.features.core.api_requests.schemas import ApiUsageSummary

router = APIRouter(prefix="/core/api-requests", tags=["core"], dependencies=[Depends(require_auth)])


@router.get("/summary", response_model=ApiUsageSummary)
async def get_api_usage_summary(
    service: ApiRequestServiceDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> ApiUsageSummary:
    return await service.get_summary(days=days)
