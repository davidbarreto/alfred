from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_auth
from app.dependencies import BudgetTargetServiceDep
from app.features.finance.budgets.schemas import (
    BudgetTargetBulkSet,
    BudgetTargetRead,
    BudgetTargetSet,
    CategoryBudgetStatus,
)

router = APIRouter(prefix="/finance/budgets", tags=["finance"], dependencies=[Depends(require_auth)])


def _parse_year_month(year_month: str | None) -> date:
    if year_month is None:
        return date.today().replace(day=1)
    try:
        year, month = (int(part) for part in year_month.split("-", 1))
        return date(year, month, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="year_month must be in YYYY-MM format")


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
    return await service.get_status(_parse_year_month(year_month))
