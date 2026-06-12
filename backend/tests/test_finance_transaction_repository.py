import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.transactions.repository import TransactionRepository
from app.features.finance.transactions.schemas import TransactionCreate, TransactionUpdate, TransactionFilters


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    r = MagicMock()
    r.scalars.return_value.first.return_value = value
    return r


def _scalar_all(values):
    r = MagicMock()
    r.scalars.return_value.all.return_value = values
    return r


def _one_result(values):
    r = MagicMock()
    r.one.return_value = values
    return r


def _scalar_result(value):
    r = MagicMock()
    r.scalar.return_value = value
    return r


def _make_txn_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.account_id = 1
    t.amount = kwargs.get("amount", Decimal("50"))
    t.type = kwargs.get("type", "expense")
    t.date = kwargs.get("date", "2026-06-12")
    return t


class TestGet:
    async def test_found(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        assert await TransactionRepository(session).get(1) == txn

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TransactionRepository(session).get(999) is None


class TestList:
    async def test_no_filters(self):
        session = _make_session()
        txns = [_make_txn_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(txns)
        result = await TransactionRepository(session).list(TransactionFilters())
        assert len(result) == 3

    async def test_type_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(type="income"))
        session.execute.assert_called_once()

    async def test_category_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(category_id=2))
        session.execute.assert_called_once()

    async def test_account_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(account_id=1))
        session.execute.assert_called_once()

    async def test_merchant_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(merchant="Shop"))
        session.execute.assert_called_once()

    async def test_date_range_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(
            from_date=date(2026, 6, 1), to_date=date(2026, 6, 30)
        ))
        session.execute.assert_called_once()

    async def test_period_filter_applied_when_no_to_date(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).list(TransactionFilters(period="this month"))
        session.execute.assert_called_once()


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        data = TransactionCreate(
            account_id=1, date="2026-06-12T10:00:00",
            amount=Decimal("50"), currency="EUR", type="expense",
        )
        await TransactionRepository(session).create(data)
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await TransactionRepository(session).update(999, TransactionUpdate())
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_fields_and_commits(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        await TransactionRepository(session).update(1, TransactionUpdate(merchant="NewShop"))
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await TransactionRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        txn = _make_txn_orm()
        session.execute.return_value = _scalar_first(txn)
        assert await TransactionRepository(session).delete(1) is True
        session.delete.assert_called_once_with(txn)
        session.commit.assert_called_once()


class TestGetSpendingTotal:
    async def test_returns_total_and_count(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("150.00"), 3))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert total == Decimal("150.00")
        assert count == 3

    async def test_returns_zero_when_no_results(self):
        session = _make_session()
        session.execute.return_value = _one_result((0, 0))
        total, count = await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert total == Decimal("0")
        assert count == 0

    async def test_optional_filters_passed(self):
        session = _make_session()
        session.execute.return_value = _one_result((Decimal("0"), 0))
        await TransactionRepository(session).get_spending_total(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            category_id=1,
            account_id=2,
            merchant="Shop",
        )
        session.execute.assert_called_once()


class TestGetTopExpenses:
    async def test_returns_list(self):
        session = _make_session()
        txns = [_make_txn_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(txns)
        result = await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
        )
        assert len(result) == 3

    async def test_category_filter_optional(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await TransactionRepository(session).get_top_expenses(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            top_n=5,
            category_id=1,
        )
        session.execute.assert_called_once()


class TestGetCategorySpent:
    async def test_returns_decimal_total(self):
        session = _make_session()
        session.execute.return_value = _scalar_result(Decimal("80.00"))
        result = await TransactionRepository(session).get_category_spent(
            category_id=1,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
        assert result == Decimal("80.00")
