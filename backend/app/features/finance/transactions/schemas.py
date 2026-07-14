from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel

TransactionType: TypeAlias = Literal["expense", "income"]


def resolve_period(
    period: str | None,
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date]:
    """Resolve a period keyword or explicit dates into a concrete [from, to] range."""
    if from_date and to_date:
        return from_date, to_date

    today = date.today()

    if period:
        p = period.lower().strip()
        if p in ("this month", "current month"):
            start = today.replace(day=1)
            if start.month == 12:
                end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
            return start, end
        if p in ("last month", "previous month"):
            first_of_this = today.replace(day=1)
            last_of_prev = first_of_this - timedelta(days=1)
            return last_of_prev.replace(day=1), last_of_prev
        if p in ("this week", "current week"):
            start = today - timedelta(days=today.weekday())
            return start, start + timedelta(days=6)
        if p in ("last week", "previous week"):
            start_of_week = today - timedelta(days=today.weekday())
            start = start_of_week - timedelta(days=7)
            return start, start_of_week - timedelta(days=1)
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
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return start, end


class TransactionBase(BaseModel):
    account_id: int
    date: datetime
    amount: Decimal
    currency: str = "EUR"
    type: TransactionType
    category_id: int | None = None
    description: str | None = None
    merchant: str | None = None
    source: str | None = None


class TransactionCreate(TransactionBase):
    deduplication_hash: str | None = None


class TransactionUpdate(BaseModel):
    account_id: int | None = None
    date: datetime | None = None
    amount: Decimal | None = None
    currency: str | None = None
    type: TransactionType | None = None
    category_id: int | None = None
    description: str | None = None
    merchant: str | None = None


class TransactionRead(TransactionBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        type: Annotated[TransactionType | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
        account_id: Annotated[int | None, Query()] = None,
        merchant: Annotated[str | None, Query()] = None,
        from_date: Annotated[date | None, Query()] = None,
        to_date: Annotated[date | None, Query()] = None,
        period: Annotated[str | None, Query()] = None,
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.type = type
        self.category_id = category_id
        self.account_id = account_id
        self.merchant = merchant
        self.from_date = from_date
        self.to_date = to_date
        self.period = period


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
    ) -> None:
        self.period = period
        self.from_date = from_date
        self.to_date = to_date
        self.category_id = category_id
        self.account_id = account_id
        self.merchant = merchant
        self.top_n = top_n
