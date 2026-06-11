from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.tables import Budget
from app.features.finance.budgets.schemas import BudgetCreate, BudgetUpdate, BudgetFilters


class BudgetRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, budget_id: int) -> Budget | None:
        result = await self._session.execute(select(Budget).where(Budget.id == budget_id))
        return result.scalars().first()

    async def list(self, filters: BudgetFilters) -> list[Budget]:
        query = select(Budget).order_by(Budget.name)
        if filters.period is not None:
            query = query.where(Budget.period == filters.period)
        if filters.category_id is not None:
            query = query.where(Budget.category_id == filters.category_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_for_period(self, period: str) -> list[Budget]:
        result = await self._session.execute(
            select(Budget).where(Budget.period == period)
        )
        return list(result.scalars().all())

    async def create(self, data: BudgetCreate) -> Budget:
        budget = Budget(**data.model_dump())
        self._session.add(budget)
        await self._session.commit()
        await self._session.refresh(budget)
        return budget

    async def update(self, budget_id: int, data: BudgetUpdate) -> Budget | None:
        budget = await self.get(budget_id)
        if budget is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(budget, field, value)
        await self._session.commit()
        await self._session.refresh(budget)
        return budget

    async def delete(self, budget_id: int) -> bool:
        budget = await self.get(budget_id)
        if budget is None:
            return False
        await self._session.delete(budget)
        await self._session.commit()
        return True
