from decimal import Decimal
from typing import Annotated, Literal, TypeAlias
from fastapi import Query
from pydantic import BaseModel

AccountType: TypeAlias = Literal["checking", "savings", "credit", "investment", "cash", "other"]


class AccountBase(BaseModel):
    name: str
    type: AccountType
    currency: str = "EUR"
    balance: Decimal = Decimal("0")
    institution: str | None = None
    is_active: bool = True


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    name: str | None = None
    type: AccountType | None = None
    currency: str | None = None
    balance: Decimal | None = None
    institution: str | None = None
    is_active: bool | None = None


class AccountRead(AccountBase):
    id: int

    model_config = {"from_attributes": True}


class AccountFilters:
    def __init__(
        self,
        is_active: Annotated[bool | None, Query()] = None,
        type: Annotated[AccountType | None, Query()] = None,
        currency: Annotated[str | None, Query()] = None,
    ) -> None:
        self.is_active = is_active
        self.type = type
        self.currency = currency
