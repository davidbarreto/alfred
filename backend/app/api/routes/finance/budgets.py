from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import BudgetServiceDep
from app.features.finance.budgets.schemas import (
    BudgetCreate,
    BudgetFilters,
    BudgetRead,
    BudgetRemainingResponse,
    BudgetUpdate,
)

router = APIRouter(prefix="/finance/budgets", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
async def create_budget(request: BudgetCreate, service: BudgetServiceDep):
    return await service.create(request)


@router.get("", response_model=list[BudgetRead])
async def list_budgets(service: BudgetServiceDep, filters: BudgetFilters = Depends()):
    return await service.list(filters)


@router.get("/remaining", response_model=list[BudgetRemainingResponse])
async def budget_remaining(
    service: BudgetServiceDep,
    period: str | None = None,
    category_id: int | None = None,
):
    return await service.remaining(period=period, category_id=category_id)


@router.get("/{budget_id}", response_model=BudgetRead)
async def get_budget(budget_id: int, service: BudgetServiceDep):
    budget = await service.get(budget_id)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget


@router.patch("/{budget_id}", response_model=BudgetRead)
async def update_budget(budget_id: int, request: BudgetUpdate, service: BudgetServiceDep):
    budget = await service.update(budget_id, request)
    if budget is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return budget


@router.delete("/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: int, service: BudgetServiceDep):
    deleted = await service.delete(budget_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Budget not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
