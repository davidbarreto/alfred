from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.errors import ShoppingItemAlreadyPendingError
from app.features.organizer.shopping.frequency import average_interval_days, next_expected_on, purchase_days
from app.features.organizer.shopping.recurrence import is_recurrence_due
from app.features.organizer.shopping.repository import (
    RecurrenceRepository,
    ShoppingRepository,
    WishlistRepository,
)
from app.features.organizer.shopping.schemas import (
    CategoryPurchaseRead,
    FrequentItemFilters,
    FrequentItemRead,
    MonthlyPurchaseRead,
    PriorityCountRead,
    PurchaseFrequencyFilters,
    PurchaseFrequencyRead,
    RecurrenceItemCreate,
    RecurrenceItemRead,
    RecurrenceItemUpdate,
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemRead,
    ShoppingItemUpdate,
    ShoppingNameSuggestion,
    ShoppingPriority,
    StorePurchaseRead,
    WishlistItemCreate,
    WishlistItemFilters,
    WishlistItemRead,
    WishlistItemUpdate,
)
from app.features.organizer.shopping_categories.repository import ShoppingCategoryRepository
from app.shared.timezone import local_timezone, local_today
from app.features.organizer.shopping_products.repository import ShoppingProductRepository
from app.features.organizer.shopping_products.schemas import ShoppingProductCreate, ShoppingProductUpdate

logger = logging.getLogger(__name__)

_DEFAULT_CATEGORY_NAME = "other"


class ShoppingService:
    def __init__(self, session: AsyncSession) -> None:
        self._shopping = ShoppingRepository(session)
        self._wishlist = WishlistRepository(session)
        self._recurrence = RecurrenceRepository(session)
        self._categories = ShoppingCategoryRepository(session)
        self._products = ShoppingProductRepository(session)

    async def resolve_category_id(self, name: str | None) -> int:
        if name:
            category = await self._categories.get_by_name(name)
            if category is not None:
                return category.id
        default_category = await self._categories.get_by_name(_DEFAULT_CATEGORY_NAME)
        if default_category is None:
            raise ValueError(f"Default shopping category {_DEFAULT_CATEGORY_NAME!r} is missing")
        return default_category.id

    # --- Shopping items ---

    async def get_item(self, item_id: int) -> ShoppingItemRead | None:
        orm = await self._shopping.get(item_id)
        if orm is None:
            return None
        return ShoppingItemRead.model_validate(orm)

    async def list_items(self, filters: ShoppingItemFilters) -> list[ShoppingItemRead]:
        items = await self._shopping.list(filters)
        return [ShoppingItemRead.model_validate(item) for item in items]

    async def create_item(self, data: ShoppingItemCreate) -> ShoppingItemRead:
        """Add an entry for the product with this name (created on first use).

        Raises ShoppingItemAlreadyPendingError when the product is already on the list.
        """
        product = await self._products.get_by_name(data.name)
        if product is None:
            category_id = data.category_id or await self.resolve_category_id(None)
            product = await self._products.create(
                ShoppingProductCreate(name=data.name, category_id=category_id, default_unit=data.unit)
            )
            logger.info("Shopping product created: id=%d name=%r", product.id, product.name)
        existing = await self._shopping.get_pending_by_product(product.id)
        if existing is not None:
            raise ShoppingItemAlreadyPendingError(product.name, existing.id)
        data = data.model_copy(
            update={
                "unit": data.unit or product.default_unit,
                "quantity": data.quantity if data.quantity is not None else product.default_quantity,
            }
        )
        orm = await self._shopping.create(product.id, data)
        logger.info("Shopping item created: id=%d product_id=%d name=%r", orm.id, product.id, product.name)
        return ShoppingItemRead.model_validate(orm)

    async def update_item(self, item_id: int, data: ShoppingItemUpdate) -> ShoppingItemRead | None:
        """Update an entry. A new name or category is applied to its product (and so to its history)."""
        current = await self._shopping.get(item_id)
        if current is None:
            logger.debug("Shopping item update: id=%d not found", item_id)
            return None
        product_fields = data.model_dump(exclude_unset=True, include={"name", "category_id"})
        if product_fields:
            await self._products.update(current.product_id, ShoppingProductUpdate(**product_fields))
        orm = await self._shopping.update(item_id, data)
        if orm is None:
            return None
        logger.info("Shopping item updated: id=%d fields=%s", item_id, list(data.model_dump(exclude_unset=True)))
        return ShoppingItemRead.model_validate(orm)

    async def delete_item(self, item_id: int) -> None:
        await self._shopping.delete(item_id)
        logger.info("Shopping item deleted: id=%d", item_id)

    async def mark_bought(self, item_id: int) -> ShoppingItemRead | None:
        orm = await self._shopping.mark_bought(item_id)
        if orm is None:
            return None
        logger.info("Shopping item bought: id=%d", item_id)
        return ShoppingItemRead.model_validate(orm)

    async def mark_skipped(self, item_id: int) -> ShoppingItemRead | None:
        orm = await self._shopping.mark_skipped(item_id)
        if orm is None:
            return None
        logger.info("Shopping item skipped: id=%d", item_id)
        return ShoppingItemRead.model_validate(orm)

    async def list_frequent_items(self, filters: FrequentItemFilters) -> list[FrequentItemRead]:
        rows = await self._shopping.get_frequent(filters)
        return [
            FrequentItemRead(
                product_id=row.product_id,
                name=row.name,
                category_id=row.category_id,
                default_unit=row.default_unit,
                purchase_count=row.purchase_count,
                last_bought_at=row.last_bought_at,
            )
            for row in rows
        ]

    async def list_purchases_by_category(self) -> list[CategoryPurchaseRead]:
        rows = await self._shopping.get_purchases_by_category()
        return [CategoryPurchaseRead(category_id=row.category_id, purchase_count=row.purchase_count) for row in rows]

    async def list_purchases_by_month(self, months: int = 6) -> list[MonthlyPurchaseRead]:
        rows = await self._shopping.get_purchases_by_month(months)
        return [MonthlyPurchaseRead(month=row.month, purchase_count=row.purchase_count) for row in rows]

    async def list_purchase_frequency(self, filters: PurchaseFrequencyFilters) -> list[PurchaseFrequencyRead]:
        """How often each product is bought, most frequently bought first.

        Products with fewer than `min_purchases` purchase days are left out; those with a single
        purchase day have no interval, so they only appear when min_purchases is 1 (and sort last)."""
        rows = await self._shopping.get_bought_history(filters.category_id)
        by_product: dict[int, list[datetime]] = defaultdict(list)
        names: dict[int, tuple[str, int | None]] = {}
        for row in rows:
            by_product[row.product_id].append(row.last_bought_at)
            names[row.product_id] = (row.name, row.category_id)

        tz, today = local_timezone(), local_today()
        result: list[PurchaseFrequencyRead] = []
        for product_id, moments in by_product.items():
            days = purchase_days(moments, tz)
            if len(days) < filters.min_purchases:
                continue
            average = average_interval_days(days)
            name, category_id = names[product_id]
            result.append(
                PurchaseFrequencyRead(
                    product_id=product_id,
                    name=name,
                    category_id=category_id,
                    purchase_count=len(days),
                    first_bought_on=days[0],
                    last_bought_on=days[-1],
                    avg_interval_days=round(average, 1) if average is not None else None,
                    days_since_last=(today - days[-1]).days,
                    next_expected_on=next_expected_on(days[-1], average) if average is not None else None,
                )
            )
        result.sort(key=lambda r: (r.avg_interval_days is None, r.avg_interval_days or 0, r.name.lower()))
        return result[: filters.limit]

    async def list_priority_counts(self) -> list[PriorityCountRead]:
        rows = await self._shopping.get_priority_counts()
        return [PriorityCountRead(priority=row.priority, item_count=row.item_count) for row in rows]

    async def list_purchases_by_store(self) -> list[StorePurchaseRead]:
        rows = await self._shopping.get_purchases_by_store()
        return [StorePurchaseRead(store=row.store, purchase_count=row.purchase_count) for row in rows]

    async def suggest_names(self, query: str, limit: int = 8) -> list[ShoppingNameSuggestion]:
        product_rows = await self._products.search_names(query, limit)
        wishlist_rows = await self._wishlist.search_names(query, limit)
        recurrence_rows = await self._recurrence.search_names(query, limit)

        merged: dict[str, tuple[str, int, str | None, datetime]] = {}
        for rows in (product_rows, wishlist_rows, recurrence_rows):
            for row in rows:
                name, category_id, recency = row[0], row[1], row[-1]
                default_unit = row[2] if len(row) == 4 else None
                key = name.lower()
                existing = merged.get(key)
                if existing is None or recency > existing[3]:
                    merged[key] = (name, category_id, default_unit or (existing[2] if existing else None), recency)

        ranked = sorted(merged.values(), key=lambda entry: entry[3], reverse=True)[:limit]
        return [
            ShoppingNameSuggestion(name=name, category_id=category_id, default_unit=default_unit)
            for name, category_id, default_unit, _ in ranked
        ]

    # --- Wishlist items ---

    async def get_wish(self, item_id: int) -> WishlistItemRead | None:
        orm = await self._wishlist.get(item_id)
        if orm is None:
            return None
        return WishlistItemRead.model_validate(orm)

    async def list_wishes(self, filters: WishlistItemFilters) -> list[WishlistItemRead]:
        items = await self._wishlist.list(filters)
        return [WishlistItemRead.model_validate(item) for item in items]

    async def create_wish(self, data: WishlistItemCreate) -> WishlistItemRead:
        if data.category_id is None:
            data = data.model_copy(update={"category_id": await self.resolve_category_id(None)})
        orm = await self._wishlist.create(data)
        logger.info("Wishlist item created: id=%d name=%r", orm.id, data.name)
        return WishlistItemRead.model_validate(orm)

    async def update_wish(self, item_id: int, data: WishlistItemUpdate) -> WishlistItemRead | None:
        orm = await self._wishlist.update(item_id, data)
        if orm is None:
            logger.debug("Wishlist item update: id=%d not found", item_id)
            return None
        logger.info("Wishlist item updated: id=%d", item_id)
        return WishlistItemRead.model_validate(orm)

    async def delete_wish(self, item_id: int) -> None:
        await self._wishlist.delete(item_id)
        logger.info("Wishlist item deleted: id=%d", item_id)

    async def promote_wish(self, item_id: int, priority: ShoppingPriority = "want") -> ShoppingItemRead | None:
        wish = await self._wishlist.get(item_id)
        if wish is None:
            return None
        shopping_item = await self.create_item(
            ShoppingItemCreate(
                name=wish.name,
                category_id=wish.category_id,
                priority=priority,
                estimated_price=wish.estimated_price,
                brand=wish.brand,
                url=wish.url,
                notes=wish.notes,
            )
        )
        await self._wishlist.promote(item_id)
        logger.info("Wishlist item promoted: wish_id=%d → shopping_id=%d", item_id, shopping_item.id)
        return shopping_item

    # --- Recurrence items ---

    async def get_recurrence(self, item_id: int) -> RecurrenceItemRead | None:
        orm = await self._recurrence.get(item_id)
        if orm is None:
            return None
        return RecurrenceItemRead.model_validate(orm)

    async def list_recurrences(self, active_only: bool = True) -> list[RecurrenceItemRead]:
        items = await self._recurrence.list(active_only=active_only)
        return [RecurrenceItemRead.model_validate(item) for item in items]

    async def create_recurrence(self, data: RecurrenceItemCreate) -> RecurrenceItemRead:
        if data.category_id is None:
            data = data.model_copy(update={"category_id": await self.resolve_category_id(None)})
        orm = await self._recurrence.create(data)
        logger.info("Recurrence item created: id=%d name=%r every=%d days", orm.id, data.name, data.recurrence_days)
        return RecurrenceItemRead.model_validate(orm)

    async def update_recurrence(self, item_id: int, data: RecurrenceItemUpdate) -> RecurrenceItemRead | None:
        orm = await self._recurrence.update(item_id, data)
        if orm is None:
            logger.debug("Recurrence item update: id=%d not found", item_id)
            return None
        logger.info("Recurrence item updated: id=%d", item_id)
        return RecurrenceItemRead.model_validate(orm)

    async def delete_recurrence(self, item_id: int) -> None:
        await self._recurrence.delete(item_id)
        logger.info("Recurrence item deleted: id=%d", item_id)

    async def list_due_recurrences(self) -> list[RecurrenceItemRead]:
        items = await self._recurrence.list(active_only=True)
        due = [item for item in items if is_recurrence_due(item.last_added_at, item.recurrence_days)]
        return [RecurrenceItemRead.model_validate(item) for item in due]

    async def accept_recurrence(self, item_id: int) -> ShoppingItemRead | None:
        recurrence = await self._recurrence.get(item_id)
        if recurrence is None:
            return None
        shopping_item = await self.create_item(
            ShoppingItemCreate(name=recurrence.name, category_id=recurrence.category_id, priority="need")
        )
        await self._recurrence.mark_added(item_id)
        logger.info(
            "Recurrence item accepted: recurrence_id=%d name=%r -> shopping_id=%d",
            item_id, recurrence.name, shopping_item.id,
        )
        return shopping_item
