import pytest
from unittest.mock import AsyncMock, MagicMock
from app.features.finance.categories.service import CategoryService
from app.features.finance.categories.schemas import CategoryCreate, CategoryUpdate, CategoryRead


def _make_category_orm(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", 1)
    c.name = kwargs.get("name", "Groceries")
    c.parent_id = kwargs.get("parent_id", None)
    return c


@pytest.fixture
def service():
    svc = CategoryService.__new__(CategoryService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_category_read_when_found(self, service):
        service._repo.get.return_value = _make_category_orm()
        result = await service.get(1)
        assert isinstance(result, CategoryRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_category_reads(self, service):
        service._repo.list.return_value = [_make_category_orm(id=i) for i in range(3)]
        result = await service.list()
        assert len(result) == 3
        assert all(isinstance(c, CategoryRead) for c in result)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list() == []


class TestCreate:
    async def test_returns_category_read(self, service):
        service._repo.create.return_value = _make_category_orm(name="Transport")
        result = await service.create(CategoryCreate(name="Transport"))
        assert isinstance(result, CategoryRead)
        assert result.name == "Transport"


class TestUpdate:
    async def test_returns_category_read_when_found(self, service):
        service._repo.update.return_value = _make_category_orm(name="Food")
        result = await service.update(1, CategoryUpdate(name="Food"))
        assert isinstance(result, CategoryRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, CategoryUpdate(name="X")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
