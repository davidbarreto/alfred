import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.budgets.repository import BudgetTargetRepository


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


def _make_target_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.category_id = kwargs.get("category_id", 1)
    t.amount = kwargs.get("amount", Decimal("300"))
    t.effective_from = kwargs.get("effective_from", datetime(2026, 7, 1))
    t.effective_to = kwargs.get("effective_to", None)
    return t


class TestGetOpen:
    async def test_found(self):
        session = _make_session()
        target = _make_target_orm()
        session.execute.return_value = _scalar_first(target)
        assert await BudgetTargetRepository(session).get_open(1) == target

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await BudgetTargetRepository(session).get_open(999) is None


class TestListCurrent:
    async def test_returns_open_rows(self):
        session = _make_session()
        targets = [_make_target_orm(id=i) for i in range(2)]
        session.execute.return_value = _scalar_all(targets)
        result = await BudgetTargetRepository(session).list_current()
        assert len(result) == 2


class TestListEffective:
    async def test_returns_effective_rows(self):
        session = _make_session()
        targets = [_make_target_orm(category_id=1), _make_target_orm(category_id=2, id=2)]
        session.execute.return_value = _scalar_all(targets)
        result = await BudgetTargetRepository(session).list_effective(datetime(2026, 8, 1))
        assert len(result) == 2
        session.execute.assert_called_once()


class TestAdd:
    def test_adds_to_session_without_committing(self):
        session = _make_session()
        target = BudgetTargetRepository(session).add(
            category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 7, 1)
        )
        session.add.assert_called_once_with(target)
        session.commit.assert_not_called()
        assert target.category_id == 1
        assert target.amount == Decimal("300")
        assert target.effective_from == datetime(2026, 7, 1)
