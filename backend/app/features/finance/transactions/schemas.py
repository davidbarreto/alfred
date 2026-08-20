from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel

from app.features.finance import cycle

TransactionType: TypeAlias = Literal["expense", "income", "transfer"]

# Sentinel AnalyticsFilters.currency value meaning "sum amount_eur across every
# currency" instead of filtering to one native currency.
GLOBAL_CURRENCY = "GLOBAL"


def resolve_period(
    period: str | None,
    from_date: date | None,
    to_date: date | None,
    cycle_start_day: int = 1,
) -> tuple[date, date]:
    """Resolve a period keyword or explicit dates into a concrete [from, to] range."""
    if from_date and to_date:
        return from_date, to_date

    today = date.today()

    if period:
        p = period.lower().strip()
        if p in ("this month", "current month"):
            return cycle.current_cycle_range(today, cycle_start_day)
        if p in ("last month", "previous month"):
            return cycle.previous_cycle_range(today, cycle_start_day)
        if p in ("this week", "current week"):
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if p in ("last week", "previous week"):
            start_of_week = today - timedelta(days=today.weekday())
            start = start_of_week - timedelta(days=7)
            return start, start_of_week - timedelta(days=1)
        if p in ("this quarter", "current quarter"):
            quarter_start_month = ((today.month - 1) // 3) * 3 + 1
            start = today.replace(month=quarter_start_month, day=1)
            if quarter_start_month + 3 > 12:
                end = date(start.year + 1, 1, 1) - timedelta(days=1)
            else:
                end = start.replace(month=quarter_start_month + 3, day=1) - timedelta(days=1)
            return start, end
        if p in ("this semester", "current semester"):
            semester_start_month = 1 if today.month <= 6 else 7
            start = today.replace(month=semester_start_month, day=1)
            if semester_start_month == 1:
                end = today.replace(month=6, day=30)
            else:
                end = today.replace(month=12, day=31)
            return start, end
        if p in ("this year", "current year"):
            return today.replace(month=1, day=1), today.replace(month=12, day=31)
        if p in ("last year", "previous year"):
            y = today.year - 1
            return date(y, 1, 1), date(y, 12, 31)
        if p == "today":
            return today, today
        if p == "yesterday":
            y = today - timedelta(days=1)
            return y, y

    # default: current month
    return cycle.current_cycle_range(today, cycle_start_day)


class TransactionBase(BaseModel):
    account_id: int
    date: datetime
    amount: Decimal
    currency: str = "EUR"
    type: TransactionType
    category_id: int | None = None
    description: str | None = None
    bank_description: str | None = None
    note: str | None = None
    merchant: str | None = None
    source: str | None = None
    counterpart_account_id: int | None = None
    counterpart_transaction_id: int | None = None
    """Set once this transfer is confirmed as matching a specific other transaction --
    counterpart_account_id alone can be an unconfirmed rule/user guess. Two ways this
    gets set: TransactionService.link_transfer (a user-confirmed Find Match), or an
    auto-generated mirror row (see Account.auto_mirror_transfers) -- a mirror always
    points back at the source leg that spawned it (Transaction.source == "auto_transfer"
    identifies the mirror side), and the source leg points at its mirror in return. Not
    directly user-editable when it points at/from a mirror. Spend totals and net-worth
    treat a transfer as a genuine internal move only once this is set."""
    balance_after: Decimal | None = None
    """The account's running balance immediately after this transaction, when the
    source statement reports one (e.g. ActivoBank checking, Banco Inter, Revolut).
    Not user-editable -- set only by statement imports."""
    installment_plan_id: int | None = None
    """Links this transaction to an installment plan (see finance.installment_plans),
    set by a matching ImportRule during import. Not user-editable -- not on
    TransactionUpdate, which is the public PATCH surface."""


class TransactionCreate(TransactionBase):
    deduplication_hash: str | None = None
    import_batch_id: int | None = None


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    date: datetime | None = None
    amount: Decimal | None = None
    currency: str | None = None
    type: TransactionType | None = None
    category_id: int | None = None
    description: str | None = None
    note: str | None = None
    merchant: str | None = None
    counterpart_account_id: int | None = None
    counterpart_transaction_id: int | None = None


class TransactionRead(TransactionBase):
    id: int
    import_batch_id: int | None = None
    amount_eur: Decimal | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


TransactionSort: TypeAlias = Literal[
    "date_desc", "date_asc", "amount_desc", "amount_asc", "name_asc", "name_desc"
]


class TransactionFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        type: Annotated[TransactionType | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        uncategorized: Annotated[bool, Query()] = False,
        account_id: Annotated[int | None, Query()] = None,
        merchant: Annotated[str | None, Query()] = None,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        period: Annotated[str | None, Query()] = None,
        currency: Annotated[str | None, Query()] = None,
        installment_plan_id: Annotated[int | None, Query()] = None,
        sort: Annotated[TransactionSort, Query()] = "date_desc",
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.type = type
        self.category_id = category_id
        self.uncategorized = uncategorized
        self.account_id = account_id
        self.merchant = merchant
        self.from_date = from_date
        self.to_date = to_date
        self.period = period
        self.currency = currency.upper() if currency is not None else None
        self.installment_plan_id = installment_plan_id
        self.sort = sort


class TransactionSumResponse(BaseModel):
    total: Decimal
    transaction_count: int
    currency: str


class TransactionBulkMoveRequest(BaseModel):
    """Reassign every transaction from account_id to target_account_id, optionally
    narrowed by the same filters as the transaction list (type/category/merchant/date
    range/currency). account_id is required -- bulk moves are always scoped to "every
    transaction currently on this one account [matching these filters]", never an
    unscoped cross-account bulk edit.
    """
    account_id: int
    target_account_id: int
    type: TransactionType | None = None
    category_id: int | None = None
    merchant: str | None = None
    from_date: date | None = None
    to_date: date | None = None
    period: str | None = None
    currency: str | None = None


class TransactionBulkMoveResponse(BaseModel):
    moved_count: int


class TransferLinkRequest(BaseModel):
    """Links two independently-imported transfer legs as counterparts of each other
    (see TransactionRepository.get_transfer_match_candidates) -- both transactions must
    already exist and be unmatched; no new rows are created and no balances change,
    since each leg already reflects its own account's true balance from its own
    statement import."""
    counterpart_transaction_id: int


# --- Analytics response models ---

class SpendingReportResponse(BaseModel):
    total: Decimal
    currency: str
    from_date: date
    to_date: date
    transaction_count: int


class CategorySpendingItem(BaseModel):
    category_id: int | None
    category_name: str | None
    total: Decimal
    transaction_count: int


class SpendingByCategoryResponse(BaseModel):
    items: list[CategorySpendingItem]
    from_date: date
    to_date: date
    currency: str


class SpendingOverTimeItem(BaseModel):
    period: str
    total: Decimal


class SpendingOverTimeResponse(BaseModel):
    items: list[SpendingOverTimeItem]
    from_date: date
    to_date: date
    currency: str
    group_by: str


class TransactionCountItem(BaseModel):
    period: str
    count: int
    unmatched_transfer_count: int = 0
    """Count of this period's transactions that are transfers with no confirmed
    counterpart (see TransactionRepository.get_transaction_counts) -- a signal the
    counterpart account's statement for this period may still be missing."""


class TransactionCoverageResponse(BaseModel):
    items: list[TransactionCountItem]
    from_date: date
    to_date: date
    group_by: str
    account_id: int | None


class AccountSpendingItem(BaseModel):
    account_id: int | None
    account_name: str | None
    total: Decimal
    transaction_count: int


class SpendingByAccountResponse(BaseModel):
    items: list[AccountSpendingItem]
    from_date: date
    to_date: date
    currency: str


class IncomeExpenseOverTimeItem(BaseModel):
    period: str
    income: Decimal
    expense: Decimal


class IncomeExpenseOverTimeResponse(BaseModel):
    items: list[IncomeExpenseOverTimeItem]
    from_date: date
    to_date: date
    currency: str
    group_by: str


class NetWorthHistoryItem(BaseModel):
    period: str
    total: Decimal


class NetWorthHistoryResponse(BaseModel):
    items: list[NetWorthHistoryItem]
    from_date: date | None
    to_date: date
    currency: str
    group_by: str


class NetWorthFilters:
    """Unlike AnalyticsFilters, net worth is a running balance, not a period
    total -- from_date only trims which buckets are returned (the running
    total itself is always reconstructed from the full transaction history up
    to to_date), and there's no category/merchant/top_n narrowing.
    """

    def __init__(
        self,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        currency: Annotated[str, Query()] = "EUR",
    ) -> None:
        self.from_date = from_date
        self.to_date = to_date or date.today()
        self.currency = currency.upper()


class SpendingAverageResponse(BaseModel):
    average_per_day: Decimal
    total: Decimal
    days: int
    from_date: date
    to_date: date


class SpendingTopResponse(BaseModel):
    transactions: list[TransactionRead]
    from_date: date
    to_date: date
    top_n: int


class TransactionBackfillEurResponse(BaseModel):
    updated_count: int
    failed_count: int
    remaining_count: int


class BalanceForecastResponse(BaseModel):
    current_balance: Decimal
    projected_income: Decimal
    projected_expenses: Decimal
    projected_balance: Decimal
    currency: str
    forecast_to: date


class AnalyticsFilters:
    def __init__(
        self,
        period: Annotated[str | None, Query()] = None,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        account_id: Annotated[int | None, Query()] = None,
        merchant: Annotated[str | None, Query()] = None,
        top_n: Annotated[int, Query(ge=1, le=50)] = 5,
        currency: Annotated[str, Query()] = "EUR",
    ) -> None:
        self.period = period
        self.from_date = from_date
        self.to_date = to_date
        self.category_id = category_id
        self.account_id = account_id
        self.merchant = merchant
        self.top_n = top_n
        self.currency = currency.upper()
