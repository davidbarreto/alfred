from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.auth import require_auth
from app.dependencies import (
    AccountServiceDep,
    RecurringTransactionServiceDep,
    TransactionServiceDep,
)
from app.features.finance.transactions.schemas import (
    AnalyticsFilters,
    BalanceForecastResponse,
    SpendingAverageResponse,
    SpendingByCategoryResponse,
    SpendingReportResponse,
    SpendingTopResponse,
    TransactionBulkMoveRequest,
    TransactionBulkMoveResponse,
    TransactionCreate,
    TransactionFilters,
    TransactionRead,
    TransactionUpdate,
)
from app.features.finance.transactions.service import InvalidBulkMoveError

router = APIRouter(prefix="/finance/transactions", tags=["finance"], dependencies=[Depends(require_auth)])


@router.post("", response_model=TransactionRead, status_code=status.HTTP_201_CREATED)
async def create_transaction(request: TransactionCreate, service: TransactionServiceDep):
    return await service.create(request)


@router.get("", response_model=list[TransactionRead])
async def list_transactions(
    service: TransactionServiceDep, filters: TransactionFilters = Depends()
):
    return await service.list(filters)


@router.post("/bulk-move", response_model=TransactionBulkMoveResponse)
async def bulk_move_transactions(request: TransactionBulkMoveRequest, service: TransactionServiceDep):
    try:
        moved = await service.bulk_move_account(request)
    except InvalidBulkMoveError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message)
    return TransactionBulkMoveResponse(moved_count=moved)


@router.get("/by-category", response_model=SpendingByCategoryResponse)
async def spending_by_category(
    service: TransactionServiceDep, filters: AnalyticsFilters = Depends()
):
    return await service.spending_by_category(filters)


@router.get("/report", response_model=SpendingReportResponse)
async def spending_report(
    service: TransactionServiceDep, filters: AnalyticsFilters = Depends()
):
    return await service.spending_report(filters)


@router.get("/average", response_model=SpendingAverageResponse)
async def spending_average(
    service: TransactionServiceDep, filters: AnalyticsFilters = Depends()
):
    return await service.spending_average(filters)


@router.get("/top", response_model=SpendingTopResponse)
async def spending_top(
    service: TransactionServiceDep, filters: AnalyticsFilters = Depends()
):
    return await service.spending_top(filters)


@router.get("/forecast", response_model=BalanceForecastResponse)
async def balance_forecast(
    filters: AnalyticsFilters = Depends(),
    txn_service: TransactionServiceDep = None,
    account_service: AccountServiceDep = None,
    recurring_service: RecurringTransactionServiceDep = None,
):
    from app.features.finance.accounts.schemas import AccountFilters
    from app.features.finance.recurring_transactions.schemas import RecurringTransactionFilters

    accounts = await account_service.list(AccountFilters(is_active=True))
    accounts = [a for a in accounts if a.currency == filters.currency]
    current_balance = sum(a.balance for a in accounts) if accounts else Decimal("0")

    rt_filters = RecurringTransactionFilters(active=True)
    active_recurring = [
        rt for rt in await recurring_service.list(rt_filters)
        if rt.currency == filters.currency
    ]

    # Resolve raw ORM objects for the service calculation
    from app.features.finance.recurring_transactions.repository import RecurringTransactionRepository
    from app.db.session import get_session

    projected_income, projected_expenses, forecast_to = await txn_service.balance_forecast(
        filters=filters,
        recurring_transactions=active_recurring,
    )

    return BalanceForecastResponse(
        current_balance=current_balance,
        projected_income=projected_income.quantize(Decimal("0.01")),
        projected_expenses=projected_expenses.quantize(Decimal("0.01")),
        projected_balance=(current_balance + projected_income - projected_expenses).quantize(Decimal("0.01")),
        currency=filters.currency,
        forecast_to=forecast_to,
    )


@router.get("/{transaction_id}", response_model=TransactionRead)
async def get_transaction(transaction_id: int, service: TransactionServiceDep):
    txn = await service.get(transaction_id)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: int, request: TransactionUpdate, service: TransactionServiceDep
):
    txn = await service.update(transaction_id, request)
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(transaction_id: int, service: TransactionServiceDep):
    deleted = await service.delete(transaction_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
