from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import RecurringTransactionServiceDep
from app.features.finance.recurring_transactions.schemas import (
    ProcessResult,
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)

router = APIRouter(
    prefix="/finance/recurring-transactions", tags=["finance"], dependencies=[Depends(require_auth)]
)


@router.post("/process", response_model=ProcessResult)
async def process_recurring(service: RecurringTransactionServiceDep):
    return await service.process()


@router.post("/", response_model=RecurringTransactionRead, status_code=status.HTTP_201_CREATED)
async def create_recurring(request: RecurringTransactionCreate, service: RecurringTransactionServiceDep):
    return await service.create(request)


@router.get("/", response_model=list[RecurringTransactionRead])
async def list_recurring(
    service: RecurringTransactionServiceDep, filters: RecurringTransactionFilters = Depends()
):
    return await service.list(filters)


@router.get("/{recurring_id}", response_model=RecurringTransactionRead)
async def get_recurring(recurring_id: int, service: RecurringTransactionServiceDep):
    rt = await service.get(recurring_id)
    if rt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring transaction not found")
    return rt


@router.patch("/{recurring_id}", response_model=RecurringTransactionRead)
async def update_recurring(
    recurring_id: int, request: RecurringTransactionUpdate, service: RecurringTransactionServiceDep
):
    rt = await service.update(recurring_id, request)
    if rt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring transaction not found")
    return rt


@router.delete("/{recurring_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recurring(recurring_id: int, service: RecurringTransactionServiceDep):
    deleted = await service.delete(recurring_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recurring transaction not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
