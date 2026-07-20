from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.repository import BudgetTargetRepository
from app.features.finance.budgets.schemas import (
    BudgetTargetBulkSetItem,
    BudgetTargetRead,
    CategoryBudgetStatus,
)
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)


def _month_range(year_month: date) -> tuple[date, date]:
    start = year_month.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return start, end


class BudgetTargetService:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = BudgetTargetRepository(session)
        self._category_repo = CategoryRepository(session)
        self._txn_repo = TransactionRepository(session)

    async def list_current_targets(self) -> list[BudgetTargetRead]:
        targets = await self._repo.list_current()
        return [BudgetTargetRead.model_validate(t) for t in targets]

    async def set_target(self, category_id: int, amount: Decimal | None) -> BudgetTargetRead | None:
        now = datetime.utcnow()
        open_target = await self._repo.get_open(category_id)

        if amount is None:
            if open_target is not None:
                open_target.effective_to = now
                await self._session.commit()
                logger.info("Budget target cleared: category_id=%d", category_id)
            return None

        same_month = (
            open_target is not None
            and open_target.effective_from.year == now.year
            and open_target.effective_from.month == now.month
        )
        if same_month:
            open_target.amount = amount
            await self._session.commit()
            await self._session.refresh(open_target)
            logger.info("Budget target updated in place: category_id=%d amount=%s", category_id, amount)
            return BudgetTargetRead.model_validate(open_target)

        if open_target is not None:
            open_target.effective_to = now

        new_target = self._repo.add(category_id=category_id, amount=amount, effective_from=now)
        await self._session.commit()
        await self._session.refresh(new_target)
        logger.info("Budget target set: category_id=%d amount=%s", category_id, amount)
        return BudgetTargetRead.model_validate(new_target)

    async def set_targets_bulk(self, items: list[BudgetTargetBulkSetItem]) -> list[BudgetTargetRead]:
        results = []
        for item in items:
            result = await self.set_target(item.category_id, item.amount)
            if result is not None:
                results.append(result)
        return results

    async def get_status(self, year_month: date) -> list[CategoryBudgetStatus]:
        from_date, to_date = _month_range(year_month)
        next_month_start = datetime.combine(to_date + timedelta(days=1), datetime.min.time())
        targets = await self._repo.list_effective(next_month_start)
        categories = {c.id: c.name for c in await self._category_repo.list()}

        results = []
        for target in targets:
            spent = await self._txn_repo.get_category_spent(
                category_id=target.category_id,
                from_date=from_date,
                to_date=to_date,
            )
            results.append(
                CategoryBudgetStatus(
                    category_id=target.category_id,
                    category_name=categories.get(target.category_id, ""),
                    year_month=year_month.replace(day=1),
                    limit_amount=target.amount,
                    spent=spent,
                )
            )
        return results
