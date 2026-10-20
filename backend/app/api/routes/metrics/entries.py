from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.features.metrics.entries.http_errors import ENTRY_ERRORS, to_http_error
from app.dependencies import MetricEntryServiceDep
from app.features.metrics.entries.schemas import (
    MetricEntryCreate,
    MetricEntryFilters,
    MetricEntryRead,
    MetricEntryUpdate,
)

router = APIRouter(
    prefix="/metrics/entries",
    tags=["metrics"],
    dependencies=[Depends(require_auth)],
)


@router.get("", response_model=list[MetricEntryRead])
async def get_entries(
    filters: Annotated[MetricEntryFilters, Depends()], service: MetricEntryServiceDep
) -> list[MetricEntryRead]:
    return await service.get_entries(filters)


@router.get("/open", response_model=list[MetricEntryRead])
async def get_open_entries(service: MetricEntryServiceDep) -> list[MetricEntryRead]:
    return await service.get_open_entries()


@router.get("/{entry_id}", response_model=MetricEntryRead)
async def get_entry(entry_id: int, service: MetricEntryServiceDep) -> MetricEntryRead:
    entry = await service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


@router.post("", response_model=MetricEntryRead, status_code=status.HTTP_201_CREATED)
async def create_entry(request: MetricEntryCreate, service: MetricEntryServiceDep) -> MetricEntryRead:
    try:
        return await service.create_entry(request)
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)


@router.patch("/{entry_id}", response_model=MetricEntryRead)
async def update_entry(entry_id: int, request: MetricEntryUpdate, service: MetricEntryServiceDep) -> MetricEntryRead:
    try:
        entry = await service.update_entry(entry_id, request)
    except ENTRY_ERRORS as exc:
        raise to_http_error(exc)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry


@router.post("/{entry_id}/discard", response_model=MetricEntryRead)
async def discard_entry(entry_id: int, service: MetricEntryServiceDep) -> MetricEntryRead:
    entry = await service.discard_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    return entry
