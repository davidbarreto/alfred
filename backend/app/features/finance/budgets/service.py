from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.repository import BudgetRepository
from app.features.finance.budgets.schemas import (
    BudgetCreate,
    BudgetFilters,
    BudgetRead,
    BudgetRemainingResponse,
    BudgetUpdate,
)
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import resolve_period


def _budget_date_range(budget) -> tuple[date, date]:
    """Resolve the active date range for a budget based on its period."""
    today = date.today()
    if budget.period == "custom" and budget.starts_at and budget.ends_at:
        return budget.starts_at.date(), budget.ends_at.date()
    return resolve_period(budget.period, None, None)


class BudgetService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = BudgetRepository(session)
        self._txn_repo = TransactionRepository(session)

    async def get(self, budget_id: int) -> BudgetRead | None:
        budget = await self._repo.get(budget_id)
        if budget is None:
            return None
        return BudgetRead.model_validate(budget)

    async def list(self, filters: BudgetFilters) -> list[BudgetRead]:
        budgets = await self._repo.list(filters)
        return [BudgetRead.model_validate(b) for b in budgets]

    async def create(self, data: BudgetCreate) -> BudgetRead:
        budget = await self._repo.create(data)
        return BudgetRead.model_validate(budget)

    async def update(self, budget_id: int, data: BudgetUpdate) -> BudgetRead | None:
        budget = await self._repo.update(budget_id, data)
        if budget is None:
            return None
        return BudgetRead.model_validate(budget)

    async def delete(self, budget_id: int) -> bool:
        return await self._repo.delete(budget_id)

    async def remaining(
        self,
        period: str | None = None,
        category_id: int | None = None,
    ) -> list[BudgetRemainingResponse]:
        filters = BudgetFilters(period=period, category_id=category_id)
        budgets = await self._repo.list(filters)
        results = []
        for budget in budgets:
            from_date, to_date = _budget_date_range(budget)
            spent = await self._txn_repo.get_category_spent(
                category_id=budget.category_id,
                from_date=from_date,
                to_date=to_date,
            ) if budget.category_id else Decimal("0")
            results.append(
                BudgetRemainingResponse(
                    budget_id=budget.id,
                    budget_name=budget.name,
                    budget_amount=budget.amount,
                    spent=spent,
                    remaining=budget.amount - spent,
                    period=budget.period,
                    from_date=from_date,
                    to_date=to_date,
                )
            )
        return results
