from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class BudgetTargetRead(BaseModel):
    id: int
    category_id: int
    amount: Decimal
    effective_from: datetime
    effective_to: datetime | None

    model_config = {"from_attributes": True}


class BudgetTargetSet(BaseModel):
    amount: Decimal | None = None


class BudgetTargetBulkSetItem(BaseModel):
    category_id: int
    amount: Decimal | None = None


class BudgetTargetBulkSet(BaseModel):
    targets: list[BudgetTargetBulkSetItem]


class CategoryBudgetStatus(BaseModel):
    category_id: int
    category_name: str
    year_month: date
    limit_amount: Decimal | None
    spent: Decimal
