from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import Query
from pydantic import BaseModel, computed_field

from app.features.finance.transactions.schemas import TransactionType


def _format_rule(rule: str) -> str:
    parts = {k: v for k, v in (p.split("=", 1) for p in rule.upper().split(";") if "=" in p)}
    freq = parts.get("FREQ", "")
    interval = int(parts.get("INTERVAL", "1"))

    if freq == "WEEKLY" and interval == 2:
        label = "Biweekly"
    else:
        label = freq.capitalize()

    until = parts.get("UNTIL")
    count = parts.get("COUNT")
    if until and len(until) >= 8:
        label += f" until {until[:4]}-{until[4:6]}-{until[6:8]}"
    elif count:
        label += f" ×{count}"

    return label


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
    last_occurrence_date: date | None = None

    @computed_field
    @property
    def display_rule(self) -> str:
        return _format_rule(self.recurrence_rule)

    model_config = {"from_attributes": True}


class ProcessResult(BaseModel):
    created: int
    deactivated: int


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
