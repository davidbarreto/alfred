import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from app.features.finance.accounts.service import AccountService
from app.features.finance.accounts.schemas import AccountCreate, AccountUpdate, AccountFilters, AccountRead


def _make_account_orm(**kwargs):
    a = MagicMock()
    a.id = kwargs.get("id", 1)
    a.name = kwargs.get("name", "Checking")
    a.type = kwargs.get("type", "checking")
    a.currency = kwargs.get("currency", "EUR")
    a.balance = kwargs.get("balance", Decimal("0"))
    a.institution = kwargs.get("institution", None)
    a.credit_limit = kwargs.get("credit_limit", None)
    a.is_active = kwargs.get("is_active", True)
    return a


@pytest.fixture
def service():
    svc = AccountService.__new__(AccountService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_account_read_when_found(self, service):
        service._repo.get.return_value = _make_account_orm()
        result = await service.get(1)
        assert isinstance(result, AccountRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_account_reads(self, service):
        service._repo.list.return_value = [_make_account_orm(id=i) for i in range(3)]
        result = await service.list(AccountFilters())
        assert len(result) == 3
        assert all(isinstance(a, AccountRead) for a in result)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        result = await service.list(AccountFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = AccountFilters(is_active=True, type="checking")
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)


class TestCreate:
    async def test_returns_account_read(self, service):
        service._repo.create.return_value = _make_account_orm(name="Savings")
        result = await service.create(AccountCreate(name="Savings", type="savings"))
        assert isinstance(result, AccountRead)
        assert result.name == "Savings"


class TestUpdate:
    async def test_returns_account_read_when_found(self, service):
        service._repo.update.return_value = _make_account_orm(institution="New Bank")
        result = await service.update(1, AccountUpdate(institution="New Bank"))
        assert isinstance(result, AccountRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, AccountUpdate(name="X")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
