from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.accounts.tables import Account
from app.features.finance.accounts.schemas import AccountCreate, AccountUpdate, AccountFilters


class AccountRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: int) -> Account | None:
        result = await self._session.execute(select(Account).where(Account.id == account_id))
        return result.scalars().first()

    async def list(self, filters: AccountFilters) -> list[Account]:
        query = select(Account)
        if filters.is_active is not None:
            query = query.where(Account.is_active == filters.is_active)
        if filters.type is not None:
            query = query.where(Account.type == filters.type)
        if filters.currency is not None:
            query = query.where(Account.currency == filters.currency)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: AccountCreate) -> Account:
        account = Account(**data.model_dump())
        self._session.add(account)
        await self._session.commit()
        await self._session.refresh(account)
        return account

    async def update(self, account_id: int, data: AccountUpdate) -> Account | None:
        account = await self.get(account_id)
        if account is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(account, field, value)
        await self._session.commit()
        await self._session.refresh(account)
        return account

    async def delete(self, account_id: int) -> bool:
        account = await self.get(account_id)
        if account is None:
            return False
        await self._session.delete(account)
        await self._session.commit()
        return True
