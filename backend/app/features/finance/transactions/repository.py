from __future__ import annotations

from datetime import date
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.transactions.tables import Transaction
from app.features.finance.transactions.schemas import (
    TransactionCreate,
    TransactionUpdate,
    TransactionFilters,
)


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
        if filters.type is not None:
            query = query.where(Transaction.type == filters.type)
        if filters.category_id is not None:
            query = query.where(Transaction.category_id == filters.category_id)
        if filters.account_id is not None:
            query = query.where(Transaction.account_id == filters.account_id)
        if filters.merchant is not None:
            query = query.where(Transaction.merchant.ilike(f"%{filters.merchant}%"))
        if filters.from_date is not None:
            query = query.where(Transaction.date >= filters.from_date)
        if filters.to_date is not None:
            query = query.where(Transaction.date <= filters.to_date)
        elif filters.period is not None:
            from app.features.finance.transactions.schemas import resolve_period
            from_dt, to_dt = resolve_period(filters.period, filters.from_date, filters.to_date)
            query = query.where(Transaction.date >= from_dt).where(Transaction.date <= to_dt)
        query = query.offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: TransactionCreate) -> Transaction:
        transaction = Transaction(**data.model_dump())
        self._session.add(transaction)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def update(self, transaction_id: int, data: TransactionUpdate) -> Transaction | None:
        transaction = await self.get(transaction_id)
        if transaction is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(transaction, field, value)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def add(self, data: TransactionCreate) -> Transaction:
        """Add transaction to session without committing. Caller is responsible for commit."""
        transaction = Transaction(**data.model_dump())
        self._session.add(transaction)
        return transaction

    async def exists_by_dedup_hash(self, dedup_hash: str) -> bool:
        result = await self._session.execute(
            select(Transaction.id).where(Transaction.deduplication_hash == dedup_hash)
        )
        return result.scalar() is not None

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
    ) -> tuple[Decimal, int]:
        query = select(
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
        ).where(
            Transaction.type == "expense",
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
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
    ) -> list[Transaction]:
        query = (
            select(Transaction)
            .where(
                Transaction.type == "expense",
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .order_by(Transaction.amount.desc())
            .limit(top_n)
        )
        if category_id is not None:
            query = query.where(Transaction.category_id == category_id)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_spending_by_category(
        self,
        from_date: date,
        to_date: date,
        account_id: int | None = None,
    ) -> list[tuple[int | None, str | None, Decimal, int]]:
        from app.features.finance.categories.tables import Category

        query = (
            select(
                Transaction.category_id,
                Category.name,
                func.coalesce(func.sum(Transaction.amount), 0),
                func.count(Transaction.id),
            )
            .outerjoin(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.type == "expense",
                Transaction.date >= from_date,
                Transaction.date <= to_date,
            )
            .group_by(Transaction.category_id, Category.name)
            .order_by(func.sum(Transaction.amount).desc())
        )
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
    ) -> Decimal:
        query = select(
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            Transaction.type == "expense",
            Transaction.category_id == category_id,
            Transaction.date >= from_date,
            Transaction.date <= to_date,
        )
        result = await self._session.execute(query)
        return Decimal(str(result.scalar()))
