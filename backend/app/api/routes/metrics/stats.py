from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import MetricStatsServiceDep
from app.features.metrics.stats.schemas import MetricStats, MetricStatsFilters

router = APIRouter(
    prefix="/metrics/series",
    tags=["metrics"],
    dependencies=[Depends(require_auth)],
)


@router.get("/{name}/stats", response_model=MetricStats)
async def get_series_stats(
    name: str, filters: Annotated[MetricStatsFilters, Depends()], service: MetricStatsServiceDep
) -> MetricStats:
    stats = await service.get_stats(name.strip().lower(), tag=filters.tag, days=filters.days)
    if stats is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return stats
