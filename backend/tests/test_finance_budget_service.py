import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.budgets.service import BudgetTargetService, _month_range
from app.features.finance.budgets.schemas import BudgetTargetRead, CategoryBudgetStatus

FIXED_NOW = datetime(2026, 7, 15, 12, 0, 0)


def _make_category_orm(id, name):
    c = MagicMock()
    c.id = id
    c.name = name  # MagicMock(name=...) is reserved for the mock's repr, not an attribute
    return c


def _make_target_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.category_id = kwargs.get("category_id", 1)
    t.amount = kwargs.get("amount", Decimal("300.00"))
    t.effective_from = kwargs.get("effective_from", datetime(2026, 7, 1))
    t.effective_to = kwargs.get("effective_to", None)
    return t


@pytest.fixture
def service():
    svc = BudgetTargetService.__new__(BudgetTargetService)
    svc._session = AsyncMock()
    svc._repo = AsyncMock()
    svc._repo.add = MagicMock()  # add() is sync in the real repository
    svc._category_repo = AsyncMock()
    svc._txn_repo = AsyncMock()
    return svc


class TestMonthRange:
    def test_regular_month(self):
        start, end = _month_range(date(2026, 7, 10))
        assert start == date(2026, 7, 1)
        assert end == date(2026, 7, 31)

    def test_december_rollover(self):
        start, end = _month_range(date(2026, 12, 5))
        assert start == date(2026, 12, 1)
        assert end == date(2026, 12, 31)


class TestListCurrentTargets:
    async def test_returns_budget_target_reads(self, service):
        service._repo.list_current.return_value = [_make_target_orm(id=i) for i in range(3)]
        result = await service.list_current_targets()
        assert len(result) == 3
        assert all(isinstance(t, BudgetTargetRead) for t in result)


class TestSetTarget:
    async def test_first_ever_target_creates_open_row(self, service):
        service._repo.get_open.return_value = None
        new_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=FIXED_NOW)
        service._repo.add.return_value = new_target

        with patch("app.features.finance.budgets.service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = FIXED_NOW
            result = await service.set_target(1, Decimal("300"))

        service._repo.add.assert_called_once_with(category_id=1, amount=Decimal("300"), effective_from=FIXED_NOW)
        assert isinstance(result, BudgetTargetRead)

    async def test_same_month_edit_updates_in_place(self, service):
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 7, 1))
        service._repo.get_open.return_value = open_target

        with patch("app.features.finance.budgets.service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = FIXED_NOW
            result = await service.set_target(1, Decimal("450"))

        assert open_target.amount == Decimal("450")
        assert open_target.effective_to is None
        service._repo.add.assert_not_called()
        assert isinstance(result, BudgetTargetRead)

    async def test_new_month_edit_closes_old_and_opens_new(self, service):
        open_target = _make_target_orm(category_id=1, amount=Decimal("300"), effective_from=datetime(2026, 6, 10))
        service._repo.get_open.return_value = open_target
        new_target = _make_target_orm(category_id=1, amount=Decimal("450"), effective_from=FIXED_NOW)
        service._repo.add.return_value = new_target

        with patch("app.features.finance.budgets.service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = FIXED_NOW
            result = await service.set_target(1, Decimal("450"))

        assert open_target.effective_to == FIXED_NOW
        service._repo.add.assert_called_once_with(category_id=1, amount=Decimal("450"), effective_from=FIXED_NOW)
        assert isinstance(result, BudgetTargetRead)

    async def test_clear_closes_open_row_and_returns_none(self, service):
        open_target = _make_target_orm(category_id=1, effective_from=datetime(2026, 7, 1))
        service._repo.get_open.return_value = open_target

        with patch("app.features.finance.budgets.service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = FIXED_NOW
            result = await service.set_target(1, None)

        assert open_target.effective_to == FIXED_NOW
        service._repo.add.assert_not_called()
        assert result is None

    async def test_clear_with_no_open_row_is_noop(self, service):
        service._repo.get_open.return_value = None
        result = await service.set_target(1, None)
        service._session.commit.assert_not_called()
        assert result is None


class TestSetTargetsBulk:
    async def test_sets_each_item_and_skips_cleared(self, service):
        service._repo.get_open.return_value = None
        service._repo.add.side_effect = [
            _make_target_orm(category_id=1, amount=Decimal("100")),
            _make_target_orm(category_id=2, amount=Decimal("200")),
        ]
        from app.features.finance.budgets.schemas import BudgetTargetBulkSetItem

        items = [
            BudgetTargetBulkSetItem(category_id=1, amount=Decimal("100")),
            BudgetTargetBulkSetItem(category_id=2, amount=Decimal("200")),
            BudgetTargetBulkSetItem(category_id=3, amount=None),
        ]
        results = await service.set_targets_bulk(items)
        assert len(results) == 2


class TestGetStatus:
    async def test_builds_status_per_effective_target(self, service):
        target = _make_target_orm(category_id=1, amount=Decimal("300.00"))
        service._repo.list_effective.return_value = [target]
        service._category_repo.list.return_value = [_make_category_orm(1, "Groceries")]
        service._txn_repo.get_category_spent.return_value = Decimal("120.00")

        results = await service.get_status(date(2026, 7, 1))

        assert len(results) == 1
        assert isinstance(results[0], CategoryBudgetStatus)
        assert results[0].category_id == 1
        assert results[0].category_name == "Groceries"
        assert results[0].limit_amount == Decimal("300.00")
        assert results[0].spent == Decimal("120.00")
        assert results[0].year_month == date(2026, 7, 1)

    async def test_passes_exclusive_next_month_boundary(self, service):
        service._repo.list_effective.return_value = []
        service._category_repo.list.return_value = []

        await service.get_status(date(2026, 7, 15))

        called_with = service._repo.list_effective.call_args[0][0]
        assert called_with == datetime(2026, 8, 1, 0, 0, 0)

    async def test_empty_targets_returns_empty_list(self, service):
        service._repo.list_effective.return_value = []
        service._category_repo.list.return_value = []
        results = await service.get_status(date(2026, 7, 1))
        assert results == []
