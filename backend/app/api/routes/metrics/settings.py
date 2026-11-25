from fastapi import APIRouter, Depends

from app.api.auth import require_auth
from app.dependencies import MetricsSettingsServiceDep
from app.features.metrics.settings.schemas import MetricsSettingsRead, MetricsSettingsUpdate

router = APIRouter(prefix="/metrics/settings", tags=["metrics"], dependencies=[Depends(require_auth)])


@router.get("", response_model=MetricsSettingsRead)
async def get_metrics_settings(service: MetricsSettingsServiceDep) -> MetricsSettingsRead:
    return await service.get()


@router.put("", response_model=MetricsSettingsRead)
async def update_metrics_settings(request: MetricsSettingsUpdate, service: MetricsSettingsServiceDep) -> MetricsSettingsRead:
    return await service.update(request)
