import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.exc import IntegrityError
from app.features.organizer.shopping_categories.service import (
    ShoppingCategoryDeletionBlockedError,
    ShoppingCategoryService,
)
from app.features.organizer.shopping_categories.schemas import (
    ShoppingCategoryCreate,
    ShoppingCategoryUpdate,
    ShoppingCategoryRead,
)


def _make_category_orm(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", 1)
    c.name = kwargs.get("name", "grocery")
    return c


@pytest.fixture
def service():
    svc = ShoppingCategoryService.__new__(ShoppingCategoryService)
    svc._repo = AsyncMock()
    svc._shopping_repo = AsyncMock()
    svc._wishlist_repo = AsyncMock()
    svc._recurrence_repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_category_read_when_found(self, service):
        service._repo.get.return_value = _make_category_orm()
        result = await service.get(1)
        assert isinstance(result, ShoppingCategoryRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_category_reads(self, service):
        service._repo.list.return_value = [_make_category_orm(id=i) for i in range(3)]
        result = await service.list()
        assert len(result) == 3
        assert all(isinstance(c, ShoppingCategoryRead) for c in result)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list() == []


class TestCreate:
    async def test_returns_category_read(self, service):
        service._repo.create.return_value = _make_category_orm(name="frozen")
        result = await service.create(ShoppingCategoryCreate(name="frozen"))
        assert isinstance(result, ShoppingCategoryRead)
        assert result.name == "frozen"


class TestUpdate:
    async def test_returns_category_read_when_found(self, service):
        service._repo.update.return_value = _make_category_orm(name="produce")
        result = await service.update(1, ShoppingCategoryUpdate(name="produce"))
        assert isinstance(result, ShoppingCategoryRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, ShoppingCategoryUpdate(name="X")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.get.return_value = _make_category_orm()
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.delete(999) is False
        service._repo.delete.assert_not_called()

    async def test_raises_blocked_error_with_counts_on_integrity_error(self, service):
        service._repo.get.return_value = _make_category_orm(id=1, name="grocery")
        service._repo.delete.side_effect = IntegrityError("stmt", {}, Exception("restrict"))
        service._shopping_repo.count_by_category.return_value = 2
        service._wishlist_repo.count_by_category.return_value = 1
        service._recurrence_repo.count_by_category.return_value = 0

        with pytest.raises(ShoppingCategoryDeletionBlockedError) as exc_info:
            await service.delete(1)

        assert exc_info.value.category_id == 1
        assert exc_info.value.shopping_count == 2
        assert exc_info.value.wishlist_count == 1
        assert exc_info.value.recurrence_count == 0
