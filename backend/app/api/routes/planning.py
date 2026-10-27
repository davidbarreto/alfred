from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.auth import require_auth
from app.dependencies import DayPlanServiceDep, PlanningSettingsServiceDep, SavedPlanServiceDep
from app.features.planning.saved_plans.schemas import DayPlansSave, SavedDayPlanRead
from app.features.planning.saved_plans.service import (
    SavedPlanConflictError,
    SavedPlanNotFoundError,
    SavedPlanValidationError,
)
from app.features.planning.schemas import DayPlanRead, PlanningSettingsRead, PlanningSettingsUpdate
from app.features.planning.service import MAX_DAYS

router = APIRouter(prefix="/planning", tags=["planning"], dependencies=[Depends(require_auth)])

_SOURCE_BY_CLIENT = {"web": "portal"}


def _source(request: Request) -> str:
    return _SOURCE_BY_CLIENT.get(request.headers.get("x-alfred-client", ""), "mcp")


def _http_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, SavedPlanConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, SavedPlanNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    else:
        code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(exc))


@router.get("/settings", response_model=PlanningSettingsRead)
async def get_planning_settings(service: PlanningSettingsServiceDep):
    return await service.get()


@router.put("/settings", response_model=PlanningSettingsRead)
async def update_planning_settings(request: PlanningSettingsUpdate, service: PlanningSettingsServiceDep):
    return await service.update(request)


@router.get("/day", response_model=DayPlanRead, response_model_exclude_none=True)
async def get_day_plan(
    service: DayPlanServiceDep,
    date: Annotated[date | None, Query(description="First local date to plan; defaults to today")] = None,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS, description="Number of consecutive days (1-7)")] = 1,
    work_minutes: Annotated[int | None, Query(ge=0, le=1440, description="Override the daily work target")] = None,
):
    return await service.get_plan(date, days, work_minutes)


@router.post("/saved", response_model=list[SavedDayPlanRead], status_code=status.HTTP_201_CREATED)
async def save_day_plans(request: Request, body: DayPlansSave, service: SavedPlanServiceDep):
    try:
        return await service.save(body, _source(request))
    except (SavedPlanValidationError, SavedPlanConflictError) as exc:
        raise _http_error(exc)


@router.get("/saved/history", response_model=list[SavedDayPlanRead])
async def get_saved_history(
    service: SavedPlanServiceDep, date: Annotated[date, Query(description="Local date whose versions to list")],
):
    return await service.get_history(date)


@router.get("/saved", response_model=list[SavedDayPlanRead])
async def get_saved_plans(
    service: SavedPlanServiceDep,
    from_date: Annotated[date, Query(alias="from", description="First local date (inclusive)")],
    to_date: Annotated[date, Query(alias="to", description="Last local date (inclusive)")],
    version: Annotated[int | None, Query(ge=1, description="A specific version instead of the active one")] = None,
):
    try:
        return await service.get_saved(from_date, to_date, version)
    except SavedPlanValidationError as exc:
        raise _http_error(exc)


@router.post("/saved/{plan_id}/archive", response_model=SavedDayPlanRead)
async def archive_saved_plan(plan_id: int, service: SavedPlanServiceDep):
    try:
        return await service.archive(plan_id)
    except (SavedPlanNotFoundError, SavedPlanConflictError) as exc:
        raise _http_error(exc)


@router.post("/saved/{plan_id}/restore", response_model=SavedDayPlanRead)
async def restore_saved_plan(plan_id: int, service: SavedPlanServiceDep):
    try:
        return await service.restore(plan_id)
    except (SavedPlanNotFoundError, SavedPlanConflictError) as exc:
        raise _http_error(exc)


@router.delete("/saved/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_saved_plan(plan_id: int, service: SavedPlanServiceDep):
    try:
        await service.delete(plan_id)
    except SavedPlanNotFoundError as exc:
        raise _http_error(exc)


@router.post("/saved/{plan_id}/blocks/{index}/missed", response_model=SavedDayPlanRead)
async def mark_block_missed(plan_id: int, index: int, service: SavedPlanServiceDep):
    try:
        return await service.set_block_missed(plan_id, index, True)
    except SavedPlanNotFoundError as exc:
        raise _http_error(exc)


@router.delete("/saved/{plan_id}/blocks/{index}/missed", response_model=SavedDayPlanRead)
async def unmark_block_missed(plan_id: int, index: int, service: SavedPlanServiceDep):
    try:
        return await service.set_block_missed(plan_id, index, False)
    except SavedPlanNotFoundError as exc:
        raise _http_error(exc)
