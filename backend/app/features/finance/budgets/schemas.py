from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class BudgetTargetRead(BaseModel):
    id: int
    category_id: int | None = None
    tag_id: int | None = None
    amount: Decimal
    effective_from: datetime
    effective_to: datetime | None

    model_config = {"from_attributes": True}


class BudgetTargetSet(BaseModel):
    amount: Decimal | None = None


class BudgetTargetBulkSetItem(BaseModel):
    category_id: int
    amount: Decimal | None = None


class TagBudgetTargetBulkSetItem(BaseModel):
    tag_id: int
    amount: Decimal | None = None


class BudgetTargetBulkSet(BaseModel):
    targets: list[BudgetTargetBulkSetItem]
    tag_targets: list[TagBudgetTargetBulkSetItem] = []


class CategoryBudgetStatus(BaseModel):
    category_id: int
    category_name: str
    year_month: date
    limit_amount: Decimal | None
    spent: Decimal


class TagBudgetStatus(BaseModel):
    tag_id: int
    tag_name: str
    year_month: date
    limit_amount: Decimal
    spent: Decimal
    overlap_count: int = 0
    """Transactions this cycle that carry this tag and also a tag with an older budget.
    They count toward the older budget, so they are left out of `spent`."""


class CurrentPeriodResponse(BaseModel):
    year_month: str
    from_date: date
    to_date: date


class CategoryAverageSpend(BaseModel):
    category_id: int
    category_name: str
    average: Decimal
    months: int


class BudgetHistoryCycle(BaseModel):
    year_month: str
    from_date: date
    to_date: date
    items: list[CategoryBudgetStatus]
    tag_items: list[TagBudgetStatus] = []
