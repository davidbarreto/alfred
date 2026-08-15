from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import BudgetTargetServiceDep
from app.features.finance.budgets.schemas import (
    BudgetTargetBulkSet,
    BudgetTargetRead,
    BudgetTargetSet,
    CategoryBudgetStatus,
    CurrentPeriodResponse,
)

router = APIRouter(prefix="/finance/budgets", tags=["finance"], dependencies=[Depends(require_auth)])


@router.get("/targets", response_model=list[BudgetTargetRead])
async def list_budget_targets(service: BudgetTargetServiceDep):
    return await service.list_current_targets()


@router.put("/targets", response_model=list[BudgetTargetRead])
async def set_budget_targets_bulk(request: BudgetTargetBulkSet, service: BudgetTargetServiceDep):
    return await service.set_targets_bulk(request.targets)


@router.put("/targets/{category_id}", response_model=BudgetTargetRead | None)
async def set_budget_target(category_id: int, request: BudgetTargetSet, service: BudgetTargetServiceDep):
    return await service.set_target(category_id, request.amount)


@router.get("/status", response_model=list[CategoryBudgetStatus])
async def budget_status(service: BudgetTargetServiceDep, year_month: str | None = None):
    try:
        return await service.get_status(year_month)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="year_month must be in YYYY-MM format")


@router.get("/current-period", response_model=CurrentPeriodResponse)
async def current_budget_period(service: BudgetTargetServiceDep):
    return CurrentPeriodResponse(year_month=await service.current_period_label())
