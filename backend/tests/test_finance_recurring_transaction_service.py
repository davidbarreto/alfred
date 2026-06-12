import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from app.features.finance.recurring_transactions.service import RecurringTransactionService
from app.features.finance.recurring_transactions.schemas import (
    RecurringTransactionCreate,
    RecurringTransactionFilters,
    RecurringTransactionRead,
    RecurringTransactionUpdate,
)


def _make_rt_orm(**kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.account_id = kwargs.get("account_id", 1)
    r.category_id = kwargs.get("category_id", None)
    r.type = kwargs.get("type", "expense")
    r.amount = kwargs.get("amount", Decimal("9.99"))
    r.currency = kwargs.get("currency", "EUR")
    r.merchant = kwargs.get("merchant", "Streaming")
    r.recurrence_rule = kwargs.get("recurrence_rule", "monthly")
    r.active = kwargs.get("active", True)
    return r


@pytest.fixture
def service():
    svc = RecurringTransactionService.__new__(RecurringTransactionService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_read_when_found(self, service):
        service._repo.get.return_value = _make_rt_orm()
        result = await service.get(1)
        assert isinstance(result, RecurringTransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_reads(self, service):
        service._repo.list.return_value = [_make_rt_orm(id=i) for i in range(3)]
        result = await service.list(RecurringTransactionFilters())
        assert len(result) == 3
        assert all(isinstance(r, RecurringTransactionRead) for r in result)

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = RecurringTransactionFilters(active=True, type="expense")
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list(RecurringTransactionFilters()) == []


class TestCreate:
    async def test_returns_recurring_transaction_read(self, service):
        service._repo.create.return_value = _make_rt_orm()
        result = await service.create(RecurringTransactionCreate(
            account_id=1, type="expense", amount=Decimal("9.99"),
            recurrence_rule="monthly",
        ))
        assert isinstance(result, RecurringTransactionRead)


class TestUpdate:
    async def test_returns_read_when_found(self, service):
        service._repo.update.return_value = _make_rt_orm(amount=Decimal("12.99"))
        result = await service.update(1, RecurringTransactionUpdate(amount=Decimal("12.99")))
        assert isinstance(result, RecurringTransactionRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, RecurringTransactionUpdate(active=False)) is None


class TestDelete:
    async def test_passes_through_true(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_passes_through_false(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
