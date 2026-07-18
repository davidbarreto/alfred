import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import (
    AccountCreate,
    AccountFilters,
    AccountRead,
    AccountUpdate,
)
from app.features.finance.transactions.repository import TransactionRepository

logger = logging.getLogger(__name__)


class AccountDeletionBlockedError(Exception):
    """Raised when an account can't be deleted because other rows still reference it
    (transactions, recurring transactions, or import batches -- all RESTRICT, not CASCADE,
    specifically so a delete can never silently destroy financial history)."""

    def __init__(self, account_id: int, transaction_count: int) -> None:
        self.account_id = account_id
        self.transaction_count = transaction_count
        super().__init__(
            f"Account {account_id} cannot be deleted: {transaction_count} transaction(s) reference it"
        )


class AccountService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = AccountRepository(session)
        self._txn_repo = TransactionRepository(session)

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
        account = await self._repo.get(account_id)
        if account is None:
            logger.debug("Account delete: id=%d not found", account_id)
            return False
        try:
            await self._repo.delete(account_id)
        except IntegrityError:
            transaction_count = await self._txn_repo.count_by_account(account_id)
            logger.warning(
                "Account delete blocked: id=%d name=%r transaction_count=%d",
                account_id, account.name, transaction_count,
            )
            raise AccountDeletionBlockedError(account_id, transaction_count)
        logger.info("Account deleted: id=%d name=%r", account_id, account.name)
        return True
