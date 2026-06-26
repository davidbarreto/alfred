import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import (
    AccountCreate,
    AccountFilters,
    AccountRead,
    AccountUpdate,
)

logger = logging.getLogger(__name__)


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
        logger.info("Account created: id=%d name=%r", account.id, data.name)
        return AccountRead.model_validate(account)

    async def update(self, account_id: int, data: AccountUpdate) -> AccountRead | None:
        account = await self._repo.update(account_id, data)
        if account is None:
            logger.debug("Account update: id=%d not found", account_id)
            return None
        logger.info("Account updated: id=%d fields=%s", account_id, list(data.model_dump(exclude_unset=True).keys()))
        return AccountRead.model_validate(account)

    async def delete(self, account_id: int) -> bool:
        deleted = await self._repo.delete(account_id)
        if deleted:
            logger.info("Account deleted: id=%d", account_id)
        else:
            logger.debug("Account delete: id=%d not found", account_id)
        return deleted
