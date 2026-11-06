from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.auth import require_auth
from app.dependencies import BudgetTargetServiceDep
from app.features.finance.budgets.schemas import (
    BudgetHistoryCycle,
    BudgetTargetBulkSet,
    BudgetTargetRead,
    BudgetTargetSet,
    CategoryAverageSpend,
    CategoryBudgetStatus,
    CurrentPeriodResponse,
    TagBudgetStatus,
)
from app.features.finance.budgets.service import BudgetTagNotFoundError

router = APIRouter(prefix="/finance/budgets", tags=["finance"], dependencies=[Depends(require_auth)])


@router.get("/targets", response_model=list[BudgetTargetRead])
async def list_budget_targets(service: BudgetTargetServiceDep):
    return await service.list_current_targets()


@router.put("/targets", response_model=list[BudgetTargetRead])
async def set_budget_targets_bulk(request: BudgetTargetBulkSet, service: BudgetTargetServiceDep):
    try:
        return await service.set_targets_bulk(request.targets, request.tag_targets)
    except BudgetTagNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")


@router.put("/targets/{category_id}", response_model=BudgetTargetRead | None)
async def set_budget_target(category_id: int, request: BudgetTargetSet, service: BudgetTargetServiceDep):
    return await service.set_target(category_id, request.amount)


@router.put("/tag-targets/{tag_id}", response_model=BudgetTargetRead | None)
async def set_tag_budget_target(tag_id: int, request: BudgetTargetSet, service: BudgetTargetServiceDep):
    try:
        return await service.set_tag_target(tag_id, request.amount)
    except BudgetTagNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tag not found")


@router.get("/tag-status", response_model=list[TagBudgetStatus])
async def tag_budget_status(service: BudgetTargetServiceDep, year_month: str | None = None):
    try:
        return await service.get_tag_status(year_month)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="year_month must be in YYYY-MM format")


@router.get("/status", response_model=list[CategoryBudgetStatus])
async def budget_status(service: BudgetTargetServiceDep, year_month: str | None = None):
    try:
        return await service.get_status(year_month)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="year_month must be in YYYY-MM format")


@router.get("/history", response_model=list[BudgetHistoryCycle])
async def budget_history(service: BudgetTargetServiceDep, cycles: Annotated[int, Query(ge=1, le=24)] = 6):
    return await service.get_history(cycles)


@router.get("/averages", response_model=list[CategoryAverageSpend])
async def budget_averages(service: BudgetTargetServiceDep, months: Annotated[int, Query(ge=1, le=12)] = 12):
    return await service.get_average_spend(months)


@router.get("/current-period", response_model=CurrentPeriodResponse)
async def budget_period(service: BudgetTargetServiceDep, year_month: str | None = None):
    try:
        return await service.get_period(year_month)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="year_month must be in YYYY-MM format")
