from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.recurring_transactions.tables import RecurringTransaction
from app.features.finance.recurring_transactions.schemas import (
    RecurringTransactionCreate,
    RecurringTransactionUpdate,
    RecurringTransactionFilters,
)


class RecurringTransactionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, recurring_id: int) -> RecurringTransaction | None:
        result = await self._session.execute(
            select(RecurringTransaction).where(RecurringTransaction.id == recurring_id)
        )
        return result.scalars().first()

    async def list(self, filters: RecurringTransactionFilters) -> list[RecurringTransaction]:
        query = select(RecurringTransaction)
        if filters.active is not None:
            query = query.where(RecurringTransaction.active == filters.active)
        if filters.type is not None:
            query = query.where(RecurringTransaction.type == filters.type)
        if filters.account_id is not None:
            query = query.where(RecurringTransaction.account_id == filters.account_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_active(self) -> list[RecurringTransaction]:
        result = await self._session.execute(
            select(RecurringTransaction).where(RecurringTransaction.active == True)
        )
        return list(result.scalars().all())

    async def create(self, data: RecurringTransactionCreate) -> RecurringTransaction:
        recurring = RecurringTransaction(**data.model_dump())
        self._session.add(recurring)
        await self._session.commit()
        await self._session.refresh(recurring)
        return recurring

    async def update(
        self, recurring_id: int, data: RecurringTransactionUpdate
    ) -> RecurringTransaction | None:
        recurring = await self.get(recurring_id)
        if recurring is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(recurring, field, value)
        await self._session.commit()
        await self._session.refresh(recurring)
        return recurring

    async def delete(self, recurring_id: int) -> bool:
        recurring = await self.get(recurring_id)
        if recurring is None:
            return False
        await self._session.delete(recurring)
        await self._session.commit()
        return True
