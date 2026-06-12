import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.categories.schemas import CategoryCreate, CategoryUpdate


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


def _make_category_orm(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", 1)
    c.name = kwargs.get("name", "Groceries")
    c.parent_id = kwargs.get("parent_id", None)
    return c


class TestGet:
    async def test_found(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        assert await CategoryRepository(session).get(1) == category

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await CategoryRepository(session).get(999) is None


class TestList:
    async def test_returns_all(self):
        session = _make_session()
        cats = [_make_category_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(cats)
        result = await CategoryRepository(session).list()
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        assert await CategoryRepository(session).list() == []


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        await CategoryRepository(session).create(CategoryCreate(name="Transport"))
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await CategoryRepository(session).update(999, CategoryUpdate(name="X"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_field_and_commits(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        await CategoryRepository(session).update(1, CategoryUpdate(name="Food"))
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await CategoryRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        result = await CategoryRepository(session).delete(1)
        assert result is True
        session.delete.assert_called_once_with(category)
        session.commit.assert_called_once()
