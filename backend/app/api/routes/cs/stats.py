from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import CsStatsServiceDep
from app.features.cs.stats.schemas import DailyActivity, StatsSummary

router = APIRouter(prefix="/cs/stats", tags=["cs"], dependencies=[Depends(require_auth)])


@router.get("/summary", response_model=StatsSummary)
async def get_stats_summary(service: CsStatsServiceDep):
    return await service.get_summary()


@router.get("/activity", response_model=list[DailyActivity])
async def get_activity(
    service: CsStatsServiceDep, days: Annotated[int | None, Query(ge=1)] = None
):
    """days omitted means unbounded ("always")."""
    return await service.get_activity(days)
