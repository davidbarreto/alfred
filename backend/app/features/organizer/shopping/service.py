from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.repository import (
    RecurrenceRepository,
    ShoppingRepository,
    WishlistRepository,
)
from app.features.organizer.shopping.schemas import (
    FrequentItemFilters,
    FrequentItemRead,
    RecurrenceItemCreate,
    RecurrenceItemRead,
    RecurrenceItemUpdate,
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemRead,
    ShoppingItemUpdate,
    ShoppingPriority,
    WishlistItemCreate,
    WishlistItemFilters,
    WishlistItemRead,
    WishlistItemUpdate,
)

logger = logging.getLogger(__name__)


class ShoppingService:
    def __init__(self, session: AsyncSession) -> None:
        self._shopping = ShoppingRepository(session)
        self._wishlist = WishlistRepository(session)
        self._recurrence = RecurrenceRepository(session)

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
        orm = await self._shopping.create(data)
        logger.info("Shopping item created: id=%d name=%r", orm.id, data.name)
        return ShoppingItemRead.model_validate(orm)

    async def update_item(self, item_id: int, data: ShoppingItemUpdate) -> ShoppingItemRead | None:
        orm = await self._shopping.update(item_id, data)
        if orm is None:
            logger.debug("Shopping item update: id=%d not found", item_id)
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
                name=row.name,
                category=row.category,
                purchase_count=row.purchase_count,
                last_bought_at=row.last_bought_at,
            )
            for row in rows
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
        shopping_item = await self._shopping.create(
            ShoppingItemCreate(
                name=wish.name,
                category=wish.category,
                priority=priority,
                estimated_price=wish.estimated_price,
                brand=wish.brand,
                url=wish.url,
                notes=wish.notes,
            )
        )
        await self._wishlist.promote(item_id)
        logger.info("Wishlist item promoted: wish_id=%d → shopping_id=%d", item_id, shopping_item.id)
        return ShoppingItemRead.model_validate(shopping_item)

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
