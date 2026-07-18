import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from app.features.finance.currencies.service import CurrencyService, DuplicateCurrencyError
from app.features.finance.currencies.schemas import CurrencyCreate, CurrencyUpdate, CurrencyRead


def _make_currency_orm(**kwargs):
    c = MagicMock()
    c.code = kwargs.get("code", "EUR")
    c.symbol = kwargs.get("symbol", "€")
    c.name = kwargs.get("name", "Euro")
    return c


@pytest.fixture
def service():
    svc = CurrencyService.__new__(CurrencyService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_currency_read_when_found(self, service):
        service._repo.get.return_value = _make_currency_orm()
        result = await service.get("eur")
        assert isinstance(result, CurrencyRead)
        assert result.code == "EUR"
        service._repo.get.assert_called_once_with("EUR")

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get("XYZ") is None


class TestList:
    async def test_returns_list_of_currency_reads(self, service):
        service._repo.list.return_value = [_make_currency_orm(code=c) for c in ("BRL", "EUR", "USD")]
        result = await service.list()
        assert len(result) == 3
        assert all(isinstance(c, CurrencyRead) for c in result)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list() == []


class TestCreate:
    async def test_returns_currency_read(self, service):
        service._repo.create.return_value = _make_currency_orm(code="PLN", symbol="zł", name="Polish Zloty")
        result = await service.create(CurrencyCreate(code="PLN", symbol="zł", name="Polish Zloty"))
        assert isinstance(result, CurrencyRead)
        assert result.code == "PLN"

    async def test_raises_duplicate_error_on_integrity_error(self, service):
        service._repo.create.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        with pytest.raises(DuplicateCurrencyError):
            await service.create(CurrencyCreate(code="EUR"))


class TestUpdate:
    async def test_returns_currency_read_when_found(self, service):
        service._repo.update.return_value = _make_currency_orm(name="Euro (EU)")
        result = await service.update("eur", CurrencyUpdate(name="Euro (EU)"))
        assert isinstance(result, CurrencyRead)
        service._repo.update.assert_called_once_with("EUR", CurrencyUpdate(name="Euro (EU)"))

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update("XYZ", CurrencyUpdate(name="X")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete("EUR") is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete("XYZ") is False
