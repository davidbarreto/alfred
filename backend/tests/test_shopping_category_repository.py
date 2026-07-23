import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.features.organizer.shopping_categories.repository import ShoppingCategoryRepository
from app.features.organizer.shopping_categories.schemas import ShoppingCategoryCreate, ShoppingCategoryUpdate


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
    c.name = kwargs.get("name", "grocery")
    return c


class TestGet:
    async def test_found(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        assert await ShoppingCategoryRepository(session).get(1) == category

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await ShoppingCategoryRepository(session).get(999) is None


class TestGetByName:
    async def test_found_case_insensitive(self):
        session = _make_session()
        category = _make_category_orm(name="grocery")
        session.execute.return_value = _scalar_first(category)
        result = await ShoppingCategoryRepository(session).get_by_name("GROCERY")
        assert result == category

    async def test_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await ShoppingCategoryRepository(session).get_by_name("nonexistent") is None


class TestList:
    async def test_returns_all(self):
        session = _make_session()
        cats = [_make_category_orm(id=i) for i in range(3)]
        session.execute.return_value = _scalar_all(cats)
        result = await ShoppingCategoryRepository(session).list()
        assert len(result) == 3

    async def test_empty(self):
        session = _make_session()
        session.execute.return_value = _scalar_all([])
        assert await ShoppingCategoryRepository(session).list() == []


class TestCreate:
    async def test_adds_commits_and_refreshes(self):
        session = _make_session()
        await ShoppingCategoryRepository(session).create(ShoppingCategoryCreate(name="frozen"))
        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()


class TestUpdate:
    async def test_returns_none_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        result = await ShoppingCategoryRepository(session).update(999, ShoppingCategoryUpdate(name="X"))
        assert result is None
        session.commit.assert_not_called()

    async def test_applies_field_and_commits(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        await ShoppingCategoryRepository(session).update(1, ShoppingCategoryUpdate(name="produce"))
        session.commit.assert_called_once()


class TestDelete:
    async def test_returns_false_when_not_found(self):
        session = _make_session()
        session.execute.return_value = _scalar_first(None)
        assert await ShoppingCategoryRepository(session).delete(999) is False

    async def test_deletes_and_returns_true(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        result = await ShoppingCategoryRepository(session).delete(1)
        assert result is True
        session.delete.assert_called_once_with(category)
        session.commit.assert_called_once()

    async def test_reraises_and_rolls_back_on_integrity_error(self):
        session = _make_session()
        category = _make_category_orm()
        session.execute.return_value = _scalar_first(category)
        session.commit.side_effect = IntegrityError("stmt", {}, Exception("restrict"))
        with pytest.raises(IntegrityError):
            await ShoppingCategoryRepository(session).delete(1)
        session.rollback.assert_called_once()
