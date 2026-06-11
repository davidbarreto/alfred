from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel

BudgetPeriod: TypeAlias = Literal["monthly", "weekly", "yearly", "custom"]


class BudgetBase(BaseModel):
    name: str
    category_id: int | None = None
    amount: Decimal
    period: BudgetPeriod
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    name: str | None = None
    category_id: int | None = None
    amount: Decimal | None = None
    period: BudgetPeriod | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class BudgetRead(BudgetBase):
    id: int

    model_config = {"from_attributes": True}


class BudgetRemainingResponse(BaseModel):
    budget_id: int
    budget_name: str
    budget_amount: Decimal
    spent: Decimal
    remaining: Decimal
    period: str
    from_date: date
    to_date: date


class BudgetFilters:
    def __init__(
        self,
        period: Annotated[BudgetPeriod | None, Query()] = None,
        category_id: Annotated[int | None, Query()] = None,
    ) -> None:
        self.period = period
        self.category_id = category_id
