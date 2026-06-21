from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.shopping.schemas import (
    RecurrenceItemCreate,
    RecurrenceItemRead,
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemRead,
    ShoppingItemUpdate,
    WishlistItemCreate,
    WishlistItemRead,
    WishlistItemFilters,
    WishlistItemUpdate,
)
from app.features.organizer.shopping.service import ShoppingService


_NOW = datetime(2026, 6, 21, 10, 0, 0, tzinfo=timezone.utc)


def _make_shopping_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.name = kwargs.get("name", "Beans")
    item.category = kwargs.get("category", "grocery")
    item.priority = kwargs.get("priority", "need")
    item.quantity = kwargs.get("quantity", None)
    item.unit = kwargs.get("unit", None)
    item.estimated_price = kwargs.get("estimated_price", None)
    item.brand = kwargs.get("brand", None)
    item.store = kwargs.get("store", None)
    item.url = kwargs.get("url", None)
    item.notes = kwargs.get("notes", None)
    item.status = kwargs.get("status", "pending")
    item.last_bought_at = kwargs.get("last_bought_at", None)
    item.created_at = kwargs.get("created_at", _NOW)
    item.updated_at = kwargs.get("updated_at", _NOW)
    return item


def _make_wishlist_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.name = kwargs.get("name", "Headphones")
    item.category = kwargs.get("category", "electronics")
    item.estimated_price = kwargs.get("estimated_price", None)
    item.brand = kwargs.get("brand", None)
    item.url = kwargs.get("url", None)
    item.notes = kwargs.get("notes", None)
    item.created_at = kwargs.get("created_at", _NOW)
    item.updated_at = kwargs.get("updated_at", _NOW)
    return item


def _make_recurrence_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.name = kwargs.get("name", "Milk")
    item.category = kwargs.get("category", "grocery")
    item.recurrence_days = kwargs.get("recurrence_days", 7)
    item.last_added_at = kwargs.get("last_added_at", None)
    item.active = kwargs.get("active", True)
    item.created_at = kwargs.get("created_at", _NOW)
    item.updated_at = kwargs.get("updated_at", _NOW)
    return item


@pytest.fixture
def service():
    svc = ShoppingService(session=AsyncMock())
    svc._shopping = AsyncMock()
    svc._wishlist = AsyncMock()
    svc._recurrence = AsyncMock()
    return svc


# --- Shopping items ---

class TestGetItem:
    async def test_returns_read_when_found(self, service):
        service._shopping.get.return_value = _make_shopping_orm()
        result = await service.get_item(1)
        assert isinstance(result, ShoppingItemRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._shopping.get.return_value = None
        result = await service.get_item(999)
        assert result is None


class TestListItems:
    async def test_returns_list_of_reads(self, service):
        service._shopping.list.return_value = [_make_shopping_orm(id=i) for i in range(3)]
        result = await service.list_items(ShoppingItemFilters())
        assert len(result) == 3
        assert all(isinstance(i, ShoppingItemRead) for i in result)

    async def test_empty_list(self, service):
        service._shopping.list.return_value = []
        result = await service.list_items(ShoppingItemFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._shopping.list.return_value = []
        filters = ShoppingItemFilters(status="bought", category="grocery")
        await service.list_items(filters)
        service._shopping.list.assert_called_once_with(filters)


class TestCreateItem:
    async def test_returns_shopping_item_read(self, service):
        service._shopping.create.return_value = _make_shopping_orm(name="Beans")
        result = await service.create_item(ShoppingItemCreate(name="Beans", category="grocery"))
        assert isinstance(result, ShoppingItemRead)
        assert result.name == "Beans"

    async def test_delegates_to_repo(self, service):
        service._shopping.create.return_value = _make_shopping_orm()
        data = ShoppingItemCreate(name="Eggs", category="grocery")
        await service.create_item(data)
        service._shopping.create.assert_called_once_with(data)


class TestUpdateItem:
    async def test_returns_updated_read(self, service):
        service._shopping.update.return_value = _make_shopping_orm(priority="want")
        result = await service.update_item(1, ShoppingItemUpdate(priority="want"))
        assert isinstance(result, ShoppingItemRead)

    async def test_returns_none_when_not_found(self, service):
        service._shopping.update.return_value = None
        result = await service.update_item(999, ShoppingItemUpdate(priority="want"))
        assert result is None


class TestDeleteItem:
    async def test_delegates_to_repo(self, service):
        await service.delete_item(1)
        service._shopping.delete.assert_called_once_with(1)


class TestMarkBought:
    async def test_returns_updated_item(self, service):
        service._shopping.mark_bought.return_value = _make_shopping_orm(status="bought", last_bought_at=_NOW)
        result = await service.mark_bought(1)
        assert isinstance(result, ShoppingItemRead)
        assert result.status == "bought"

    async def test_returns_none_when_not_found(self, service):
        service._shopping.mark_bought.return_value = None
        result = await service.mark_bought(999)
        assert result is None


class TestMarkSkipped:
    async def test_returns_updated_item(self, service):
        service._shopping.mark_skipped.return_value = _make_shopping_orm(status="skipped")
        result = await service.mark_skipped(1)
        assert result.status == "skipped"

    async def test_returns_none_when_not_found(self, service):
        service._shopping.mark_skipped.return_value = None
        result = await service.mark_skipped(999)
        assert result is None


# --- Wishlist ---

class TestCreateWish:
    async def test_returns_wishlist_read(self, service):
        service._wishlist.create.return_value = _make_wishlist_orm(name="Headphones")
        result = await service.create_wish(WishlistItemCreate(name="Headphones", category="electronics"))
        assert isinstance(result, WishlistItemRead)
        assert result.name == "Headphones"


class TestPromoteWish:
    async def test_creates_shopping_item_and_deletes_wish(self, service):
        wish = _make_wishlist_orm(id=5, name="Headphones", category="electronics", estimated_price=Decimal("150"))
        service._wishlist.get.return_value = wish
        service._shopping.create.return_value = _make_shopping_orm(id=10, name="Headphones", priority="want")

        result = await service.promote_wish(5, priority="want")

        assert isinstance(result, ShoppingItemRead)
        assert result.name == "Headphones"
        service._shopping.create.assert_called_once()
        service._wishlist.delete.assert_called_once_with(5)

    async def test_returns_none_when_wish_not_found(self, service):
        service._wishlist.get.return_value = None
        result = await service.promote_wish(999)
        assert result is None
        service._shopping.create.assert_not_called()

    async def test_promoted_item_uses_wish_fields(self, service):
        wish = _make_wishlist_orm(
            id=3, name="Book", category="books",
            estimated_price=Decimal("25"), brand="Penguin", url="https://example.com", notes="gift idea"
        )
        service._wishlist.get.return_value = wish
        service._shopping.create.return_value = _make_shopping_orm(id=7, name="Book")

        await service.promote_wish(3, priority="need")

        call_args = service._shopping.create.call_args[0][0]
        assert call_args.name == "Book"
        assert call_args.category == "books"
        assert call_args.priority == "need"
        assert call_args.estimated_price == Decimal("25")
        assert call_args.brand == "Penguin"


# --- Recurrence ---

class TestCreateRecurrence:
    async def test_returns_recurrence_read(self, service):
        service._recurrence.create.return_value = _make_recurrence_orm(name="Milk", recurrence_days=7)
        result = await service.create_recurrence(RecurrenceItemCreate(name="Milk", category="grocery", recurrence_days=7))
        assert isinstance(result, RecurrenceItemRead)
        assert result.recurrence_days == 7


class TestListRecurrences:
    async def test_active_only_by_default(self, service):
        service._recurrence.list.return_value = []
        await service.list_recurrences()
        service._recurrence.list.assert_called_once_with(active_only=True)

    async def test_can_include_inactive(self, service):
        service._recurrence.list.return_value = []
        await service.list_recurrences(active_only=False)
        service._recurrence.list.assert_called_once_with(active_only=False)
