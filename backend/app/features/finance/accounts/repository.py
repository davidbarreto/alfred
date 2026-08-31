from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
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
        query = select(Account).order_by(Account.name)
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

    async def set_balance(self, account_id: int, balance: Decimal) -> None:
        await self._session.execute(
            update(Account).where(Account.id == account_id).values(balance=balance)
        )
        await self._session.commit()

    async def adjust_balance(self, account_id: int, delta: Decimal) -> None:
        """Apply a signed delta to an account's balance in a single atomic UPDATE --
        avoids a read-modify-write race between concurrent transaction mutations on
        the same account."""
        await self._session.execute(
            update(Account).where(Account.id == account_id).values(balance=Account.balance + delta)
        )
        await self._session.commit()

    async def delete(self, account_id: int) -> bool:
        account = await self.get(account_id)
        if account is None:
            return False
        await self._session.delete(account)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise
        return True
