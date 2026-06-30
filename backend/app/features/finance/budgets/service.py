from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


def _budget_date_range(budget) -> tuple[date, date]:
    if budget.period == "custom" and budget.starts_at and budget.ends_at:
        return budget.starts_at.date(), budget.ends_at.date()
    today = date.today()
    if budget.period == "weekly":
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if budget.period == "yearly":
        return today.replace(month=1, day=1), today.replace(month=12, day=31)
    start = today.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return start, end


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
        logger.info("Budget created: id=%d name=%r amount=%s period=%s", budget.id, data.name, data.amount, data.period)
        return BudgetRead.model_validate(budget)

    async def update(self, budget_id: int, data: BudgetUpdate) -> BudgetRead | None:
        budget = await self._repo.update(budget_id, data)
        if budget is None:
            logger.debug("Budget update: id=%d not found", budget_id)
            return None
        logger.info("Budget updated: id=%d fields=%s", budget_id, list(data.model_dump(exclude_unset=True).keys()))
        return BudgetRead.model_validate(budget)

    async def delete(self, budget_id: int) -> bool:
        deleted = await self._repo.delete(budget_id)
        if deleted:
            logger.info("Budget deleted: id=%d", budget_id)
        else:
            logger.debug("Budget delete: id=%d not found", budget_id)
        return deleted

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
