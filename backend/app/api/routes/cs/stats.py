from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import CsStatsServiceDep
from app.features.cs.stats.schemas import StatsSummary

router = APIRouter(prefix="/cs/stats", tags=["cs"], dependencies=[Depends(require_auth)])


@router.get("/summary", response_model=StatsSummary)
async def get_stats_summary(service: CsStatsServiceDep):
    return await service.get_summary()
