import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.recurring_transactions.repository import RecurringTransactionRepository
from app.features.finance.recurring_transactions.schemas import (
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionUpdate,
)


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


def _make_rt_orm(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.account_id = kwargs.get("account_id", 1)
    r.type = kwargs.get("type", "expense")
    r.amount = kwargs.get("amount", Decimal("9.99"))
    r.active = kwargs.get("active", True)
    r.recurrence_rule = "monthly"
    return r


class TestGet:
    async def test_found(self):
        session = _make_session()
        rt = _make_rt_orm()
        session.execute.return_value = _scalar_first(rt)
        assert await RecurringTransactionRepository(session).get(1) == rt

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await RecurringTransactionRepository(session).get(999) is None


class TestList:
    async def test_no_filters(self):
        session = _make_session()
        rts = [_make_rt_orm(id=i) for i in range(2)]
        session.execute.return_value = _scalar_all(rts)
        result = await RecurringTransactionRepository(session).list(RecurringTransactionFilters())
        assert len(result) == 2

    async def test_active_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await RecurringTransactionRepository(session).list(RecurringTransactionFilters(active=True))
        session.execute.assert_called_once()

    async def test_type_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await RecurringTransactionRepository(session).list(RecurringTransactionFilters(type="income"))
        session.execute.assert_called_once()

    async def test_account_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await RecurringTransactionRepository(session).list(RecurringTransactionFilters(account_id=1))
        session.execute.assert_called_once()


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        data = RecurringTransactionCreate(
            account_id=1, type="expense", amount=Decimal("9.99"), recurrence_rule="monthly",
        )
        await RecurringTransactionRepository(session).create(data)
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await RecurringTransactionRepository(session).update(
            999, RecurringTransactionUpdate(active=False)
        )
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_fields_and_commits(self):
        session = _make_session()
        rt = _make_rt_orm()
        session.execute.return_value = _scalar_first(rt)
        await RecurringTransactionRepository(session).update(
            1, RecurringTransactionUpdate(amount=Decimal("12.99"))
        )
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await RecurringTransactionRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        rt = _make_rt_orm()
        session.execute.return_value = _scalar_first(rt)
        assert await RecurringTransactionRepository(session).delete(1) is True
        session.delete.assert_called_once_with(rt)
        session.commit.assert_called_once()
