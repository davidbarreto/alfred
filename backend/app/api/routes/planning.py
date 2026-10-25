from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth import require_auth
from app.dependencies import DayPlanServiceDep, PlanningSettingsServiceDep
from app.features.planning.schemas import DayPlanRead, PlanningSettingsRead, PlanningSettingsUpdate
from app.features.planning.service import MAX_DAYS

router = APIRouter(prefix="/planning", tags=["planning"], dependencies=[Depends(require_auth)])


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
