import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.accounts.repository import AccountRepository
from app.features.finance.accounts.schemas import AccountCreate, AccountUpdate, AccountFilters


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


def _make_account_orm(**kwargs):
    a = MagicMock()
    a.id = kwargs.get("id", 1)
    a.name = kwargs.get("name", "Checking")
    a.type = kwargs.get("type", "checking")
    a.currency = kwargs.get("currency", "EUR")
    a.balance = kwargs.get("balance", Decimal("0"))
    a.institution = kwargs.get("institution", None)
    a.is_active = kwargs.get("is_active", True)
    return a


class TestGet:
    async def test_found(self):
        session = _make_session()
        account = _make_account_orm()
        session.execute.return_value = _scalar_first(account)

        repo = AccountRepository(session)
        result = await repo.get(1)

        assert result == account
        session.execute.assert_called_once()

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)

        repo = AccountRepository(session)
        assert await repo.get(999) is None


class TestList:
    async def test_returns_all_with_no_filters(self):
        session = _make_session()
        accounts = [_make_account_orm(id=i) for i in range(2)]
        session.execute.return_value = _scalar_all(accounts)

        repo = AccountRepository(session)
        result = await repo.list(AccountFilters())
        assert len(result) == 2

    async def test_is_active_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = AccountRepository(session)
        await repo.list(AccountFilters(is_active=True))
        session.execute.assert_called_once()

    async def test_type_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = AccountRepository(session)
        await repo.list(AccountFilters(type="savings"))
        session.execute.assert_called_once()

    async def test_currency_filter(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        repo = AccountRepository(session)
        await repo.list(AccountFilters(currency="USD"))
        session.execute.assert_called_once()


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        repo = AccountRepository(session)
        data = AccountCreate(name="Savings", type="savings", balance=Decimal("500"))
        await repo.create(data)

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        repo = AccountRepository(session)
        result = await repo.update(999, AccountUpdate(name="X"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_fields_and_commits(self):
        session = _make_session()
        account = _make_account_orm()
        session.execute.return_value = _scalar_first(account)
        repo = AccountRepository(session)
        await repo.update(1, AccountUpdate(institution="New Bank"))
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        repo = AccountRepository(session)
        assert await repo.delete(999) is False
        session.commit.assert_not_called()

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        account = _make_account_orm()
        session.execute.return_value = _scalar_first(account)
        repo = AccountRepository(session)
        result = await repo.delete(1)
        assert result is True
        session.delete.assert_called_once_with(account)
        session.commit.assert_called_once()

    async def test_rolls_back_and_reraises_on_integrity_error(self):
        session = _make_session()
        account = _make_account_orm()
        session.execute.return_value = _scalar_first(account)
        session.commit.side_effect = IntegrityError("", "", Exception("fk violation"))
        repo = AccountRepository(session)

        with pytest.raises(IntegrityError):
            await repo.delete(1)

        session.rollback.assert_awaited_once()
