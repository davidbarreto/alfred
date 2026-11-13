from datetime import datetime
from decimal import Decimal
from typing import Literal, TypeAlias

from pydantic import BaseModel

LinkKind: TypeAlias = Literal["legs", "stays", "visits"]


class TransactionLinkCreate(BaseModel):
    transaction_id: int


class LinkedTransaction(BaseModel):
    id: int
    date: datetime
    merchant: str | None
    description: str | None
    bank_description: str | None = None
    type: str
    amount: Decimal
    currency: str
    amount_eur: Decimal | None

    model_config = {"from_attributes": True}


class Cost(BaseModel):
    """What linked transactions add up to. Expenses count up, refunds (income) count down, in EUR."""

    total_eur: Decimal = Decimal("0.00")
    transaction_count: int = 0
    # Linked transactions with no EUR amount yet: reported, never silently counted as zero.
    unconverted_count: int = 0


class LinkedTransactions(BaseModel):
    transactions: list[LinkedTransaction]
    cost: Cost


class KindCost(Cost):
    kind: str


class EntityCost(Cost):
    id: int


class TripCosts(BaseModel):
    """`total` counts each transaction once however many items it is linked to; `by_kind` groups legs by mode,
    stays as `lodging` and visits by place kind, so a charge linked under two kinds appears under both."""

    total: Cost
    by_kind: list[KindCost]
    legs: list[EntityCost]
    stays: list[EntityCost]
    visits: list[EntityCost]


class PlaceCosts(BaseModel):
    """Lifetime cost of a place: its visits plus (for a hotel) its stays."""

    total: Cost


class ApplyDefaultTagsResult(BaseModel):
    tags: list[str]
    # Transaction-tag rows added; expenses that already carried a tag are not counted for it.
    added: int
