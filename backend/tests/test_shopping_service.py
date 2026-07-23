from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.shopping.schemas import (
    FrequentItemFilters,
    FrequentItemRead,
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

_GROCERY_ID = 1
_ELECTRONICS_ID = 2
_BOOKS_ID = 3
_OTHER_ID = 8


def _make_shopping_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.name = kwargs.get("name", "Beans")
    item.category_id = kwargs.get("category_id", _GROCERY_ID)
    item.priority = kwargs.get("priority", "need")
    item.quantity = kwargs.get("quantity", None)
    item.unit = kwargs.get("unit", None)
    item.estimated_price = kwargs.get("estimated_price", None)
    item.brand = kwargs.get("brand", None)
    item.store = kwargs.get("store", None)
    item.url = kwargs.get("url", None)
    item.notes = kwargs.get("notes", None)
    item.status = kwargs.get("status", "pending")
    item.source = kwargs.get("source", None)
    item.last_bought_at = kwargs.get("last_bought_at", None)
    item.created_at = kwargs.get("created_at", _NOW)
    item.updated_at = kwargs.get("updated_at", _NOW)
    return item


def _make_wishlist_orm(**kwargs):
    item = MagicMock()
    item.id = kwargs.get("id", 1)
    item.name = kwargs.get("name", "Headphones")
    item.category_id = kwargs.get("category_id", _ELECTRONICS_ID)
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
    item.category_id = kwargs.get("category_id", _GROCERY_ID)
    item.recurrence_days = kwargs.get("recurrence_days", 7)
    item.last_added_at = kwargs.get("last_added_at", None)
    item.active = kwargs.get("active", True)
    item.created_at = kwargs.get("created_at", _NOW)
    item.updated_at = kwargs.get("updated_at", _NOW)
    return item


def _make_category_orm(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", _OTHER_ID)
    c.name = kwargs.get("name", "other")
    return c


@pytest.fixture
def service():
    svc = ShoppingService(session=AsyncMock())
    svc._shopping = AsyncMock()
    svc._wishlist = AsyncMock()
    svc._recurrence = AsyncMock()
    svc._categories = AsyncMock()
    svc._categories.get_by_name.return_value = _make_category_orm()
    return svc


# --- Category resolution ---

class TestResolveCategoryId:
    async def test_returns_matching_category_id_when_found(self, service):
        service._categories.get_by_name.return_value = _make_category_orm(id=_GROCERY_ID, name="grocery")
        result = await service.resolve_category_id("grocery")
        assert result == _GROCERY_ID
        service._categories.get_by_name.assert_called_once_with("grocery")

    async def test_falls_back_to_other_when_name_is_none(self, service):
        async def get_by_name(name):
            return _make_category_orm(id=_OTHER_ID, name="other") if name == "other" else None

        service._categories.get_by_name.side_effect = get_by_name
        result = await service.resolve_category_id(None)
        assert result == _OTHER_ID

    async def test_falls_back_to_other_when_name_is_blank(self, service):
        async def get_by_name(name):
            return _make_category_orm(id=_OTHER_ID, name="other") if name == "other" else None

        service._categories.get_by_name.side_effect = get_by_name
        result = await service.resolve_category_id("")
        assert result == _OTHER_ID

    async def test_falls_back_to_other_when_name_unmatched(self, service):
        async def get_by_name(name):
            return _make_category_orm(id=_OTHER_ID, name="other") if name == "other" else None

        service._categories.get_by_name.side_effect = get_by_name
        result = await service.resolve_category_id("not-a-real-category")
        assert result == _OTHER_ID

    async def test_raises_when_default_category_missing(self, service):
        service._categories.get_by_name.return_value = None
        with pytest.raises(ValueError):
            await service.resolve_category_id(None)


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
        filters = ShoppingItemFilters(status="bought", category_id=_GROCERY_ID)
        await service.list_items(filters)
        service._shopping.list.assert_called_once_with(filters)


class TestCreateItem:
    async def test_returns_shopping_item_read(self, service):
        service._shopping.create.return_value = _make_shopping_orm(name="Beans")
        result = await service.create_item(ShoppingItemCreate(name="Beans", category_id=_GROCERY_ID))
        assert isinstance(result, ShoppingItemRead)
        assert result.name == "Beans"

    async def test_delegates_to_repo_when_category_given(self, service):
        service._shopping.create.return_value = _make_shopping_orm()
        data = ShoppingItemCreate(name="Eggs", category_id=_GROCERY_ID)
        await service.create_item(data)
        service._shopping.create.assert_called_once_with(data)

    async def test_resolves_other_category_when_omitted(self, service):
        service._categories.get_by_name.return_value = _make_category_orm(id=_OTHER_ID, name="other")
        service._shopping.create.return_value = _make_shopping_orm(category_id=_OTHER_ID)
        data = ShoppingItemCreate(name="Eggs")
        await service.create_item(data)
        called_with = service._shopping.create.call_args[0][0]
        assert called_with.category_id == _OTHER_ID


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


class TestListFrequentItems:
    async def test_returns_list_of_reads(self, service):
        row = SimpleNamespace(name="Milk", category_id=_GROCERY_ID, purchase_count=5, last_bought_at=_NOW)
        service._shopping.get_frequent.return_value = [row]

        result = await service.list_frequent_items(FrequentItemFilters())

        assert len(result) == 1
        assert isinstance(result[0], FrequentItemRead)
        assert result[0].name == "Milk"
        assert result[0].purchase_count == 5

    async def test_empty_when_no_history(self, service):
        service._shopping.get_frequent.return_value = []
        result = await service.list_frequent_items(FrequentItemFilters())
        assert result == []

    async def test_passes_filters_to_repo(self, service):
        service._shopping.get_frequent.return_value = []
        filters = FrequentItemFilters(category_id=_GROCERY_ID, limit=5)
        await service.list_frequent_items(filters)
        service._shopping.get_frequent.assert_called_once_with(filters)


# --- Wishlist ---

class TestCreateWish:
    async def test_returns_wishlist_read(self, service):
        service._wishlist.create.return_value = _make_wishlist_orm(name="Headphones")
        result = await service.create_wish(WishlistItemCreate(name="Headphones", category_id=_ELECTRONICS_ID))
        assert isinstance(result, WishlistItemRead)
        assert result.name == "Headphones"


class TestPromoteWish:
    async def test_creates_shopping_item_and_promotes_wish(self, service):
        wish = _make_wishlist_orm(id=5, name="Headphones", category_id=_ELECTRONICS_ID, estimated_price=Decimal("150"))
        service._wishlist.get.return_value = wish
        service._shopping.create.return_value = _make_shopping_orm(id=10, name="Headphones", priority="want")

        result = await service.promote_wish(5, priority="want")

        assert isinstance(result, ShoppingItemRead)
        assert result.name == "Headphones"
        service._shopping.create.assert_called_once()
        service._wishlist.promote.assert_called_once_with(5)

    async def test_returns_none_when_wish_not_found(self, service):
        service._wishlist.get.return_value = None
        result = await service.promote_wish(999)
        assert result is None
        service._shopping.create.assert_not_called()

    async def test_promoted_item_uses_wish_fields(self, service):
        wish = _make_wishlist_orm(
            id=3, name="Book", category_id=_BOOKS_ID,
            estimated_price=Decimal("25"), brand="Penguin", url="https://example.com", notes="gift idea"
        )
        service._wishlist.get.return_value = wish
        service._shopping.create.return_value = _make_shopping_orm(id=7, name="Book")

        await service.promote_wish(3, priority="need")

        call_args = service._shopping.create.call_args[0][0]
        assert call_args.name == "Book"
        assert call_args.category_id == _BOOKS_ID
        assert call_args.priority == "need"
        assert call_args.estimated_price == Decimal("25")
        assert call_args.brand == "Penguin"


# --- Recurrence ---

class TestCreateRecurrence:
    async def test_returns_recurrence_read(self, service):
        service._recurrence.create.return_value = _make_recurrence_orm(name="Milk", recurrence_days=7)
        result = await service.create_recurrence(RecurrenceItemCreate(name="Milk", category_id=_GROCERY_ID, recurrence_days=7))
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
