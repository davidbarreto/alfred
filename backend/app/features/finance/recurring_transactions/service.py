from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.recurring_transactions.repository import RecurringTransactionRepository
from app.features.finance.recurring_transactions.schemas import (
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)


class RecurringTransactionService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = RecurringTransactionRepository(session)

    async def get(self, recurring_id: int) -> RecurringTransactionRead | None:
        rt = await self._repo.get(recurring_id)
        if rt is None:
            return None
        return RecurringTransactionRead.model_validate(rt)

    async def list(self, filters: RecurringTransactionFilters) -> list[RecurringTransactionRead]:
        rts = await self._repo.list(filters)
        return [RecurringTransactionRead.model_validate(r) for r in rts]

    async def create(self, data: RecurringTransactionCreate) -> RecurringTransactionRead:
        rt = await self._repo.create(data)
        return RecurringTransactionRead.model_validate(rt)

    async def update(
        self, recurring_id: int, data: RecurringTransactionUpdate
    ) -> RecurringTransactionRead | None:
        rt = await self._repo.update(recurring_id, data)
        if rt is None:
            return None
        return RecurringTransactionRead.model_validate(rt)

    async def delete(self, recurring_id: int) -> bool:
        return await self._repo.delete(recurring_id)
