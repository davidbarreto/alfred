from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.shopping.errors import ShoppingProductBlockedError
from app.features.organizer.shopping_products.schemas import (
    ShoppingProductCreate,
    ShoppingProductFilters,
    ShoppingProductRead,
    ShoppingProductUpdate,
)
from app.features.organizer.shopping_products.service import ShoppingProductService

_NOW = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
_OTHER_ID = 8


def _product(**kwargs):
    product = MagicMock()
    product.id = kwargs.get("id", 1)
    product.name = kwargs.get("name", "Milk")
    product.category_id = kwargs.get("category_id", 1)
    product.default_unit = kwargs.get("default_unit", "l")
    product.default_quantity = kwargs.get("default_quantity", None)
    product.created_at = _NOW
    product.updated_at = _NOW
    return product


@pytest.fixture
def service():
    svc = ShoppingProductService(session=AsyncMock())
    svc._repo = AsyncMock()
    svc._categories = AsyncMock()
    svc._categories.get_by_name.return_value = MagicMock(id=_OTHER_ID)
    return svc


class TestList:
    async def test_adds_purchase_count_and_pending_flag(self, service):
        service._repo.list.return_value = [(_product(id=1), 6, True), (_product(id=2, name="Rice"), 0, False)]

        result = await service.list(ShoppingProductFilters())

        assert [(p.name, p.purchase_count, p.pending) for p in result] == [("Milk", 6, True), ("Rice", 0, False)]


class TestCreate:
    async def test_defaults_category_to_other(self, service):
        service._repo.create.return_value = _product()

        await service.create(ShoppingProductCreate(name="Milk"))

        assert service._repo.create.call_args[0][0].category_id == _OTHER_ID

    async def test_keeps_given_category_and_unit(self, service):
        service._repo.create.return_value = _product()

        await service.create(ShoppingProductCreate(name="Milk", category_id=3, default_unit="l"))

        data = service._repo.create.call_args[0][0]
        assert (data.category_id, data.default_unit) == (3, "l")
        service._categories.get_by_name.assert_not_called()

    def test_name_whitespace_is_collapsed_and_blank_rejected(self):
        assert ShoppingProductCreate(name="  Olive   oil ").name == "Olive oil"
        with pytest.raises(ValueError):
            ShoppingProductCreate(name="   ")


class TestUpdate:
    async def test_returns_read(self, service):
        service._repo.update.return_value = _product(default_unit="kg", default_quantity=Decimal("1"))

        result = await service.update(1, ShoppingProductUpdate(default_unit="kg"))

        assert isinstance(result, ShoppingProductRead)
        assert result.default_unit == "kg"

    async def test_none_when_missing(self, service):
        service._repo.update.return_value = None
        assert await service.update(9, ShoppingProductUpdate(name="x")) is None


class TestDelete:
    async def test_blocked_while_pending(self, service):
        service._repo.get.return_value = _product()
        service._repo.has_pending.return_value = True

        with pytest.raises(ShoppingProductBlockedError):
            await service.delete(1)

        service._repo.delete.assert_not_called()

    async def test_deletes_when_not_pending(self, service):
        service._repo.get.return_value = _product()
        service._repo.has_pending.return_value = False

        assert await service.delete(1) is True
        service._repo.delete.assert_awaited_once_with(1)

    async def test_false_when_missing(self, service):
        service._repo.get.return_value = None
        assert await service.delete(1) is False


class TestMerge:
    async def test_repoints_entries_then_deletes_source(self, service):
        service._repo.get.side_effect = lambda pid: _product(id=pid)
        service._repo.has_pending.side_effect = lambda pid: pid == 1

        result = await service.merge(1, 2)

        service._repo.repoint_items.assert_awaited_once_with(1, 2)
        service._repo.delete.assert_awaited_once_with(1)
        assert result.id == 2

    async def test_blocked_when_both_are_pending(self, service):
        service._repo.get.side_effect = lambda pid: _product(id=pid)
        service._repo.has_pending.return_value = True

        with pytest.raises(ShoppingProductBlockedError):
            await service.merge(1, 2)

        service._repo.repoint_items.assert_not_called()

    async def test_cannot_merge_into_itself(self, service):
        with pytest.raises(ShoppingProductBlockedError):
            await service.merge(1, 1)

    async def test_none_when_either_is_missing(self, service):
        service._repo.get.side_effect = lambda pid: _product(id=pid) if pid == 1 else None
        assert await service.merge(1, 2) is None
        service._repo.repoint_items.assert_not_called()
