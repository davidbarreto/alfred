from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import (
    AccountCreate,
    AccountFilters,
    AccountRead,
    AccountUpdate,
)


class AccountService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AccountRepository(session)

    async def get(self, account_id: int) -> AccountRead | None:
        account = await self._repo.get(account_id)
        if account is None:
            return None
        return AccountRead.model_validate(account)

    async def list(self, filters: AccountFilters) -> list[AccountRead]:
        accounts = await self._repo.list(filters)
        return [AccountRead.model_validate(a) for a in accounts]

    async def create(self, data: AccountCreate) -> AccountRead:
        account = await self._repo.create(data)
        return AccountRead.model_validate(account)

    async def update(self, account_id: int, data: AccountUpdate) -> AccountRead | None:
        account = await self._repo.update(account_id, data)
        if account is None:
            return None
        return AccountRead.model_validate(account)

    async def delete(self, account_id: int) -> bool:
        return await self._repo.delete(account_id)
