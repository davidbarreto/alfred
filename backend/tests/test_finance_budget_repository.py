import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.budgets.repository import BudgetRepository
from app.features.finance.budgets.schemas import BudgetCreate, BudgetUpdate, BudgetFilters


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


def _make_budget_orm(**kwargs):
    b = MagicMock()
    b.id = kwargs.get("id", 1)
    b.name = kwargs.get("name", "Food Budget")
    b.period = kwargs.get("period", "monthly")
    b.amount = kwargs.get("amount", Decimal("300"))
    b.category_id = kwargs.get("category_id", 1)
    return b


class TestGet:
    async def test_found(self):
        session = _make_session()
        budget = _make_budget_orm()
        session.execute.return_value = _scalar_first(budget)
        assert await BudgetRepository(session).get(1) == budget

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await BudgetRepository(session).get(999) is None


class TestList:
    async def test_no_filters(self):
        session = _make_session()
        budgets = [_make_budget_orm(id=i) for i in range(2)]
        session.execute.return_value = _scalar_all(budgets)
        result = await BudgetRepository(session).list(BudgetFilters())
        assert len(result) == 2

    async def test_period_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await BudgetRepository(session).list(BudgetFilters(period="monthly"))
        session.execute.assert_called_once()

    async def test_category_id_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        await BudgetRepository(session).list(BudgetFilters(category_id=1))
        session.execute.assert_called_once()


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        data = BudgetCreate(name="Food", amount=Decimal("300"), period="monthly")
        await BudgetRepository(session).create(data)
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await BudgetRepository(session).update(999, BudgetUpdate(name="X"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_fields_and_commits(self):
        session = _make_session()
        budget = _make_budget_orm()
        session.execute.return_value = _scalar_first(budget)
        await BudgetRepository(session).update(1, BudgetUpdate(amount=Decimal("500")))
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await BudgetRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        budget = _make_budget_orm()
        session.execute.return_value = _scalar_first(budget)
        assert await BudgetRepository(session).delete(1) is True
        session.delete.assert_called_once_with(budget)
        session.commit.assert_called_once()
