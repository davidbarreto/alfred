from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.transactions.tables import Transaction
from app.features.finance.transactions.schemas import (
    GLOBAL_CURRENCY,
    TransactionBulkMoveRequest,
    TransactionCreate,
    TransactionUpdate,
    TransactionFilters,
)


def _amount_column(currency: str):
    return Transaction.amount_eur if currency == GLOBAL_CURRENCY else Transaction.amount


def _spend_condition(transaction_type: str):
    """A transfer with no tracked counterpart account is money that left an
    Alfred-tracked account and never landed in another one (e.g. sent to an external
    wallet, or converted to a currency Alfred doesn't track) -- it's effectively spent,
    even though the bank/import labeled it a transfer. A transfer that does have a
    counterpart_account_id is a genuine internal move between two tracked accounts and
    stays excluded from spend. Only applies when reporting "expense"; other types
    (income) match the column exactly.
    """
    if transaction_type == "expense":
        return or_(
            Transaction.type == "expense",
            and_(Transaction.type == "transfer", Transaction.counterpart_account_id.is_(None)),
        )
    return Transaction.type == transaction_type


def _filter_conditions(filters: Any) -> list:
    """Shared WHERE-clause building for anything shaped like TransactionFilters
    (duck-typed: also used by TransactionBulkMoveRequest, which carries the same
    optional type/category/merchant/date/currency fields plus a required account_id).
    """
    conditions = []
    if filters.type is not None:
        conditions.append(_spend_condition(filters.type))
    if getattr(filters, "uncategorized", False):
        conditions.append(Transaction.category_id.is_(None))
    elif filters.category_id is not None:
        conditions.append(Transaction.category_id == filters.category_id)
    if getattr(filters, "account_id", None) is not None:
        conditions.append(Transaction.account_id == filters.account_id)
    if filters.merchant is not None:
        conditions.append(Transaction.merchant.ilike(f"%{filters.merchant}%"))
    if filters.currency is not None and filters.currency != GLOBAL_CURRENCY:
        conditions.append(Transaction.currency == filters.currency)
    if filters.from_date is not None:
        conditions.append(Transaction.date >= filters.from_date)
    if filters.to_date is not None:
        conditions.append(Transaction.date <= filters.to_date)
    elif filters.period is not None:
        from app.features.finance.transactions.schemas import resolve_period
        from_dt, to_dt = resolve_period(filters.period, filters.from_date, filters.to_date)
        conditions.append(Transaction.date >= from_dt)
        conditions.append(Transaction.date <= to_dt)
    return conditions


class TransactionRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, transaction_id: int) -> Transaction | None:
        result = await self._session.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        return result.scalars().first()

    async def list(self, filters: TransactionFilters) -> list[Transaction]:
        query = select(Transaction).order_by(Transaction.date.desc())
        for condition in _filter_conditions(filters):
            query = query.where(condition)
        query = query.offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def bulk_reassign_account(self, request: TransactionBulkMoveRequest) -> int:
        """Move every transaction matching request's account_id + optional filters to
        target_account_id. Clears deduplication_hash on moved rows: the stored hash was
        computed against the old account_id (and the source statement's balance, which
        isn't persisted), so it can no longer be trusted to detect a future re-import.
        """
        stmt = update(Transaction).values(account_id=request.target_account_id, deduplication_hash=None)
        for condition in _filter_conditions(request):
            stmt = stmt.where(condition)
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.rowcount

    async def create(self, data: TransactionCreate, amount_eur: Decimal | None = None) -> Transaction:
        transaction = Transaction(**data.model_dump(), amount_eur=amount_eur)
        self._session.add(transaction)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def update(
        self,
        transaction_id: int,
        data: TransactionUpdate,
        amount_eur: Decimal | None = None,
        recompute_amount_eur: bool = False,
    ) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(transaction, field, value)
        if recompute_amount_eur:
            transaction.amount_eur = amount_eur
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def add(self, data: TransactionCreate, amount_eur: Decimal | None = None) -> Transaction:
        """Add transaction to session without committing. Caller is responsible for commit."""
        transaction = Transaction(**data.model_dump(), amount_eur=amount_eur)
        self._session.add(transaction)
        return transaction

    async def count_by_account(self, account_id: int) -> int:
        result = await self._session.execute(
            select(func.count(Transaction.id)).where(Transaction.account_id == account_id)
        )
        return result.scalar_one()

    async def exists_by_dedup_hash(self, dedup_hash: str) -> bool:
        result = await self._session.execute(
            select(Transaction.id).where(Transaction.deduplication_hash == dedup_hash)
        )
        return result.scalar() is not None

    async def get_existing_dedup_hashes(self, dedup_hashes: list[str]) -> set[str]:
        if not dedup_hashes:
            return set()
        result = await self._session.execute(
            select(Transaction.deduplication_hash).where(
                Transaction.deduplication_hash.in_(dedup_hashes)
            )
        )
        return {row for row in result.scalars().all()}

    async def get_by_ids(self, transaction_ids: list[int]) -> list[Transaction]:
        if not transaction_ids:
            return []
        result = await self._session.execute(
            select(Transaction).where(Transaction.id.in_(transaction_ids))
        )
        return list(result.scalars().all())

    async def get_ids_by_import_batch(self, import_batch_id: int) -> list[int]:
        result = await self._session.execute(
            select(Transaction.id).where(Transaction.import_batch_id == import_batch_id)
        )
        return list(result.scalars().all())

    async def delete_by_ids(self, transaction_ids: list[int]) -> int:
        if not transaction_ids:
            return 0
        result = await self._session.execute(
            select(Transaction).where(Transaction.id.in_(transaction_ids))
        )
        transactions = list(result.scalars().all())
        for transaction in transactions:
            await self._session.delete(transaction)
        await self._session.commit()
        return len(transactions)

    async def delete(self, transaction_id: int) -> bool:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return False
        await self._session.delete(transaction)
        await self._session.commit()
        return True

    async def get_spending_total(
        self,
        from_date: date,
        to_date: date,
        category_id: int | None = None,
        account_id: int | None = None,
        merchant: str | None = None,
        currency: str = "EUR",
        transaction_type: str = "expense",
    ) -> tuple[Decimal, int]:
        amount_column = _amount_column(currency)
        query = select(
            func.coalesce(func.sum(amount_column), 0),
            func.count(Transaction.id),
        ).where(
            _spend_condition(transaction_type),
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        if merchant is not None:
            query = query.where(Transaction.merchant.ilike(f"%{merchant}%"))
        result = await self._session.execute(query)
        total, count = result.one()
        return Decimal(str(total)), count

    async def get_top_expenses(
        self,
        from_date: date,
        to_date: date,
        top_n: int,
        category_id: int | None = None,
        currency: str = "EUR",
    ) -> list[Transaction]:
        query = (
            select(Transaction)
            .where(
                _spend_condition("expense"),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .order_by(_amount_column(currency).desc())
            .limit(top_n)
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_spending_by_category(
        self,
        from_date: date,
        to_date: date,
        account_id: int | None = None,
        currency: str = "EUR",
    ) -> list[tuple[int | None, str | None, Decimal, int]]:
        from app.features.finance.categories.tables import Category

        amount_column = _amount_column(currency)
        query = (
            select(
                Transaction.category_id,
                Category.name,
                func.coalesce(func.sum(amount_column), 0),
                func.count(Transaction.id),
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                _spend_condition("expense"),
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .group_by(Transaction.category_id, Category.name)
            .order_by(func.sum(amount_column).desc())
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        result = await self._session.execute(query)
        return [
            (row[0], row[1], Decimal(str(row[2])), row[3])
            for row in result.all()
        ]

    async def get_category_spent(
        self,
        category_id: int,
        from_date: date,
        to_date: date,
        currency: str = "EUR",
    ) -> Decimal:
        query = select(
            func.coalesce(func.sum(_amount_column(currency)), 0)
        ).where(
            _spend_condition("expense"),
            Transaction.category_id == category_id,
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
        if currency != GLOBAL_CURRENCY:
            query = query.where(Transaction.currency == currency)
        result = await self._session.execute(query)
        return Decimal(str(result.scalar()))

    async def list_missing_amount_eur(self, limit: int = 1000) -> list[Transaction]:
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.amount_eur.is_(None))
            .order_by(Transaction.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def set_amount_eur(self, transaction_id: int, amount_eur: Decimal) -> None:
        await self._session.execute(
            update(Transaction).where(Transaction.id == transaction_id).values(amount_eur=amount_eur)
        )
        await self._session.commit()

    async def count_missing_amount_eur(self) -> int:
        result = await self._session.execute(
            select(func.count(Transaction.id)).where(Transaction.amount_eur.is_(None))
        )
        return result.scalar_one()
