import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from app.features.finance.budgets.service import BudgetService, _budget_date_range
from app.features.finance.budgets.schemas import (
    BudgetCreate,
    BudgetFilters,
    BudgetRead,
    BudgetUpdate,
)

FIXED_TODAY = date(2026, 6, 12)


def _make_budget_orm(**kwargs):
    b = MagicMock()
    b.id = kwargs.get("id", 1)
    b.name = kwargs.get("name", "Groceries Budget")
    b.category_id = kwargs.get("category_id", 1)
    b.amount = kwargs.get("amount", Decimal("300.00"))
    b.period = kwargs.get("period", "monthly")
    b.starts_at = kwargs.get("starts_at", None)
    b.ends_at = kwargs.get("ends_at", None)
    return b


@pytest.fixture
def service():
    svc = BudgetService.__new__(BudgetService)
    svc._repo = AsyncMock()
    svc._txn_repo = AsyncMock()
    return svc


class TestBudgetDateRange:
    def test_custom_with_explicit_dates(self):
        budget = _make_budget_orm(
            period="custom",
            starts_at=datetime(2026, 3, 1),
            ends_at=datetime(2026, 3, 31),
        )
        from_d, to_d = _budget_date_range(budget)
        assert from_d == date(2026, 3, 1)
        assert to_d == date(2026, 3, 31)

    def test_monthly_uses_resolve_period(self):
        budget = _make_budget_orm(period="monthly")
        with patch("app.features.finance.budgets.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            from_d, to_d = _budget_date_range(budget)
        assert from_d == date(2026, 6, 1)
        assert to_d == date(2026, 6, 30)

    def test_custom_without_dates_falls_back_to_resolve_period(self):
        budget = _make_budget_orm(period="custom", starts_at=None, ends_at=None)
        with patch("app.features.finance.budgets.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            from_d, to_d = _budget_date_range(budget)
        assert from_d == date(2026, 6, 1)
        assert to_d == date(2026, 6, 30)


class TestGet:
    async def test_returns_budget_read_when_found(self, service):
        service._repo.get.return_value = _make_budget_orm()
        result = await service.get(1)
        assert isinstance(result, BudgetRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_budget_reads(self, service):
        service._repo.list.return_value = [_make_budget_orm(id=i) for i in range(3)]
        result = await service.list(BudgetFilters())
        assert len(result) == 3
        assert all(isinstance(b, BudgetRead) for b in result)

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = BudgetFilters(period="monthly")
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)


class TestCreate:
    async def test_returns_budget_read(self, service):
        service._repo.create.return_value = _make_budget_orm()
        result = await service.create(BudgetCreate(name="Test", amount=Decimal("100"), period="monthly"))
        assert isinstance(result, BudgetRead)


class TestUpdate:
    async def test_returns_budget_read_when_found(self, service):
        service._repo.update.return_value = _make_budget_orm(amount=Decimal("350"))
        result = await service.update(1, BudgetUpdate(amount=Decimal("350")))
        assert isinstance(result, BudgetRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, BudgetUpdate(name="X")) is None


class TestDelete:
    async def test_passes_through_true(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_passes_through_false(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False


class TestRemaining:
    async def test_budget_with_category_queries_spent(self, service):
        budget = _make_budget_orm(category_id=1, amount=Decimal("300.00"))
        service._repo.list.return_value = [budget]
        service._txn_repo.get_category_spent.return_value = Decimal("120.00")

        with patch("app.features.finance.budgets.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            results = await service.remaining()

        assert len(results) == 1
        assert results[0].spent == Decimal("120.00")
        assert results[0].remaining == Decimal("180.00")
        assert results[0].budget_id == budget.id

    async def test_budget_without_category_has_zero_spent(self, service):
        budget = _make_budget_orm(category_id=None, amount=Decimal("200.00"))
        service._repo.list.return_value = [budget]

        with patch("app.features.finance.budgets.service.date") as mock_date:
            mock_date.today.return_value = FIXED_TODAY
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            results = await service.remaining()

        service._txn_repo.get_category_spent.assert_not_called()
        assert results[0].spent == Decimal("0")
        assert results[0].remaining == Decimal("200.00")

    async def test_empty_budgets(self, service):
        service._repo.list.return_value = []
        results = await service.remaining()
        assert results == []

    async def test_filters_passed_to_repo(self, service):
        service._repo.list.return_value = []
        await service.remaining(period="monthly", category_id=2)
        call_filters = service._repo.list.call_args[0][0]
        assert call_filters.period == "monthly"
        assert call_filters.category_id == 2
