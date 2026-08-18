from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel

from app.features.finance.imports.schemas import RuleMode

InstallmentPlanStatus = Literal["open", "closed"]


class InstallmentPlanCreate(BaseModel):
    account_id: int
    description: str
    total_installments: int
    opened_date: date
    plan_ref: str | None = None
    original_amount: Decimal | None = None
    """The full, unamortized purchase price, when this plan has a lump-sum original
    transaction to match/supersede (ActivoBank PDF-derived plans always have one; a
    manually-created plan generally doesn't -- see InstallmentPlan.original_amount)."""
    # The matching rule created alongside the plan (see InstallmentPlanService) --
    # every plan is created together with an ImportRule that tags future matching
    # transactions with this plan's id, so there is exactly one mechanism ("a rule
    # matched") for how a transaction ever gets linked to a plan.
    pattern: str
    amount: Decimal | None = None
    mode: RuleMode = "auto"


class InstallmentPlanUpdate(BaseModel):
    description: str | None = None
    total_installments: int | None = None


class InstallmentPlanRead(BaseModel):
    id: int
    account_id: int
    description: str
    total_installments: int
    captured_installments: int
    """Derived (COUNT of linked, non-zero-amount transactions), not a stored column."""
    plan_ref: str | None = None
    original_amount: Decimal | None = None
    opened_date: date
    status: InstallmentPlanStatus
    total_interest_paid: Decimal
    total_duty_paid: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class InstallmentPlanFilters:
    def __init__(
        self,
        account_id: Annotated[int | None, Query()] = None,
        status: Annotated[InstallmentPlanStatus | None, Query()] = None,
    ) -> None:
        self.account_id = account_id
        self.status = status
