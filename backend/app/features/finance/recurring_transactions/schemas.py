from decimal import Decimal
from typing import Annotated
from fastapi import Query
from pydantic import BaseModel

from app.features.finance.transactions.schemas import TransactionType


class RecurringTransactionBase(BaseModel):
    account_id: int
    category_id: int | None = None
    type: TransactionType
    amount: Decimal
    currency: str = "EUR"
    merchant: str | None = None
    recurrence_rule: str
    active: bool = True


class RecurringTransactionCreate(RecurringTransactionBase):
    pass


class RecurringTransactionUpdate(BaseModel):
    account_id: int | None = None
    category_id: int | None = None
    type: TransactionType | None = None
    amount: Decimal | None = None
    currency: str | None = None
    merchant: str | None = None
    recurrence_rule: str | None = None
    active: bool | None = None


class RecurringTransactionRead(RecurringTransactionBase):
    id: int

    model_config = {"from_attributes": True}


class RecurringTransactionFilters:
    def __init__(
        self,
        active: Annotated[bool | None, Query()] = None,
        type: Annotated[TransactionType | None, Query()] = None,
        account_id: Annotated[int | None, Query()] = None,
    ) -> None:
        self.active = active
        self.type = type
        self.account_id = account_id
