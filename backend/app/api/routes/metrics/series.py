from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import MetricSeriesServiceDep
from app.features.metrics.series.schemas import (
    MetricSeriesCreate,
    MetricSeriesMerge,
    MetricSeriesRead,
    MetricSeriesSummary,
    MetricSeriesUpdate,
)
from app.features.metrics.series.service import (
    MetricSeriesMergeError,
    MetricSeriesNameTakenError,
    MetricSeriesNotEmptyError,
)

router = APIRouter(
    prefix="/metrics/series",
    tags=["metrics"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[MetricSeriesSummary])
async def get_all_series(service: MetricSeriesServiceDep, include_archived: bool = False) -> list[MetricSeriesSummary]:
    return await service.get_all_series(include_archived=include_archived)


@router.post("", response_model=MetricSeriesRead, status_code=status.HTTP_201_CREATED)
async def create_series(request: MetricSeriesCreate, service: MetricSeriesServiceDep) -> MetricSeriesRead:
    try:
        return await service.create_series(request)
    except MetricSeriesNameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A series with that name already exists")


@router.get("/{name}", response_model=MetricSeriesRead)
async def get_series(name: str, service: MetricSeriesServiceDep) -> MetricSeriesRead:
    series = await service.get_series(name.strip().lower())
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return series


@router.patch("/{name}", response_model=MetricSeriesRead)
async def update_series(name: str, request: MetricSeriesUpdate, service: MetricSeriesServiceDep) -> MetricSeriesRead:
    try:
        series = await service.update_series(name.strip().lower(), request)
    except MetricSeriesNameTakenError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A series with that name already exists")
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return series


@router.post("/{name}/merge", response_model=MetricSeriesRead)
async def merge_series(name: str, request: MetricSeriesMerge, service: MetricSeriesServiceDep) -> MetricSeriesRead:
    try:
        series = await service.merge_series(name.strip().lower(), request)
    except MetricSeriesMergeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return series


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_series(name: str, service: MetricSeriesServiceDep) -> Response:
    try:
        deleted = await service.delete_series(name.strip().lower())
    except MetricSeriesNotEmptyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Series has {exc.entry_count} entries; archive it or merge it into another series instead",
        )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
