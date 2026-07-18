import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.features.finance.currencies.repository import CurrencyRepository
from app.features.finance.currencies.schemas import CurrencyCreate, CurrencyUpdate


def _make_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


def _scalar_first(value):
    result = MagicMock()
    result.scalars.return_value.first.return_value = value
    return result


def _scalar_all(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _make_currency_orm(**kwargs):
    c = MagicMock()
    c.code = kwargs.get("code", "EUR")
    c.symbol = kwargs.get("symbol", "€")
    c.name = kwargs.get("name", "Euro")
    return c


class TestGet:
    async def test_found(self):
        session = _make_session()
        currency = _make_currency_orm()
        session.execute.return_value = _scalar_first(currency)
        assert await CurrencyRepository(session).get("EUR") == currency

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await CurrencyRepository(session).get("XYZ") is None


class TestList:
    async def test_returns_all(self):
        session = _make_session()
        currencies = [_make_currency_orm(code=c) for c in ("BRL", "EUR", "USD")]
        session.execute.return_value = _scalar_all(currencies)
        result = await CurrencyRepository(session).list()
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        assert await CurrencyRepository(session).list() == []


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        await CurrencyRepository(session).create(CurrencyCreate(code="PLN", symbol="zł", name="Polish Zloty"))
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()

    async def test_rolls_back_and_reraises_on_duplicate_code(self):
        session = _make_session()
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("dup"))
        with pytest.raises(IntegrityError):
            await CurrencyRepository(session).create(CurrencyCreate(code="EUR"))
        session.rollback.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await CurrencyRepository(session).update("XYZ", CurrencyUpdate(symbol="?"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_field_and_commits(self):
        session = _make_session()
        currency = _make_currency_orm()
        session.execute.return_value = _scalar_first(currency)
        await CurrencyRepository(session).update("EUR", CurrencyUpdate(name="Euro (EU)"))
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await CurrencyRepository(session).delete("XYZ") is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        currency = _make_currency_orm()
        session.execute.return_value = _scalar_first(currency)
        result = await CurrencyRepository(session).delete("EUR")
        assert result is True
        session.delete.assert_called_once_with(currency)
        session.commit.assert_called_once()
