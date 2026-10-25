from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import require_auth
from app.dependencies import ActivityServiceDep
from app.features.organizer.activities.schemas import (
    ActivityCreate,
    ActivityFilters,
    ActivityLogCreate,
    ActivityLogRead,
    ActivityRead,
    ActivityStats,
    ActivityUpdate,
)
from app.features.organizer.activities.service import (
    DEFAULT_STATS_WEEKS,
    MAX_STATS_WEEKS,
    ActivityStateError,
    ActivityValidationError,
)

router = APIRouter(prefix="/organizer/activities", tags=["organizer"], dependencies=[Depends(require_auth)])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")


def _http_error(exc: ValueError) -> HTTPException:
    code = status.HTTP_409_CONFLICT if isinstance(exc, ActivityStateError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(exc))


@router.post("", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
async def create_activity(request: ActivityCreate, service: ActivityServiceDep):
    return await service.create_activity(request)


@router.get("", response_model=list[ActivityRead])
async def get_activities(service: ActivityServiceDep, filters: ActivityFilters = Depends()):
    return await service.get_activities(filters)


@router.get("/stats", response_model=ActivityStats)
async def get_activity_stats(
    service: ActivityServiceDep,
    weeks: Annotated[int, Query(ge=1, le=MAX_STATS_WEEKS, description="How many weeks back, including this one")] = DEFAULT_STATS_WEEKS,
):
    return await service.get_stats(weeks)


@router.get("/{activity_id}", response_model=ActivityRead)
async def get_activity(activity_id: int, service: ActivityServiceDep):
    activity = await service.get_activity(activity_id)
    if activity is None:
        raise _NOT_FOUND
    return activity


@router.patch("/{activity_id}", response_model=ActivityRead)
async def update_activity(activity_id: int, request: ActivityUpdate, service: ActivityServiceDep):
    try:
        activity = await service.update_activity(activity_id, request)
    except ActivityValidationError as exc:
        raise _http_error(exc)
    if activity is None:
        raise _NOT_FOUND
    return activity


@router.post("/{activity_id}/archive", response_model=ActivityRead)
async def archive_activity(activity_id: int, service: ActivityServiceDep):
    activity = await service.archive(activity_id)
    if activity is None:
        raise _NOT_FOUND
    return activity


@router.post("/{activity_id}/unarchive", response_model=ActivityRead)
async def unarchive_activity(activity_id: int, service: ActivityServiceDep):
    activity = await service.unarchive(activity_id)
    if activity is None:
        raise _NOT_FOUND
    return activity


@router.post("/{activity_id}/logs", response_model=ActivityLogRead, status_code=status.HTTP_201_CREATED)
async def log_activity(activity_id: int, request: ActivityLogCreate, service: ActivityServiceDep):
    try:
        log = await service.log(activity_id, request)
    except (ActivityValidationError, ActivityStateError) as exc:
        raise _http_error(exc)
    if log is None:
        raise _NOT_FOUND
    return log


@router.get("/{activity_id}/logs", response_model=list[ActivityLogRead])
async def get_activity_logs(
    activity_id: int,
    service: ActivityServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    logs = await service.get_history(activity_id, limit, offset)
    if logs is None:
        raise _NOT_FOUND
    return logs
