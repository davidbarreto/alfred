from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.tables import BudgetTarget


class BudgetTargetRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_open(self, category_id: int) -> BudgetTarget | None:
        result = await self._session.execute(
            select(BudgetTarget).where(
                BudgetTarget.category_id == category_id,
                BudgetTarget.effective_to.is_(None),
            )
        )
        return result.scalars().first()

    async def list_current(self) -> list[BudgetTarget]:
        result = await self._session.execute(
            select(BudgetTarget).where(BudgetTarget.effective_to.is_(None))
        )
        return list(result.scalars().all())

    async def list_effective(self, cycle_start: datetime, cycle_end: datetime) -> list[BudgetTarget]:
        """The target in effect for each category during the cycle [cycle_start, cycle_end).

        One row per category: among the targets that started before the cycle
        ended and were not closed before it began, the most recently started.
        """
        result = await self._session.execute(
            select(BudgetTarget)
            .distinct(BudgetTarget.category_id)
            .where(
                BudgetTarget.effective_from < cycle_end,
                or_(BudgetTarget.effective_to.is_(None), BudgetTarget.effective_to > cycle_start),
            )
            .order_by(BudgetTarget.category_id, BudgetTarget.effective_from.desc())
        )
        return list(result.scalars().all())

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(BudgetTarget).where(BudgetTarget.category_id == category_id)
        )
        return result.scalar_one()

    def add(self, category_id: int, amount: Decimal, effective_from: datetime) -> BudgetTarget:
        """Add a new open target to the session without committing."""
        target = BudgetTarget(category_id=category_id, amount=amount, effective_from=effective_from)
        self._session.add(target)
        return target
