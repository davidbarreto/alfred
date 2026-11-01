from __future__ import annotations

import logging

from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.errors import ShoppingProductBlockedError
from app.features.organizer.shopping_categories.repository import ShoppingCategoryRepository
from app.features.organizer.shopping_products.repository import ShoppingProductRepository
from app.features.organizer.shopping_products.schemas import (
    ShoppingProductCreate,
    ShoppingProductFilters,
    ShoppingProductRead,
    ShoppingProductUpdate,
)

logger = logging.getLogger(__name__)

_DEFAULT_CATEGORY_NAME = "other"


def _to_read(row: Row) -> ShoppingProductRead:
    product, purchase_count, pending = row
    read = ShoppingProductRead.model_validate(product)
    return read.model_copy(update={"purchase_count": purchase_count, "pending": bool(pending)})


class ShoppingProductService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ShoppingProductRepository(session)
        self._categories = ShoppingCategoryRepository(session)

    async def get(self, product_id: int) -> ShoppingProductRead | None:
        product = await self._repo.get(product_id)
        if product is None:
            return None
        return ShoppingProductRead.model_validate(product)

    async def list(self, filters: ShoppingProductFilters) -> list[ShoppingProductRead]:
        rows = await self._repo.list(filters)
        return [_to_read(row) for row in rows]

    async def create(self, data: ShoppingProductCreate) -> ShoppingProductRead:
        if data.category_id is None:
            default = await self._categories.get_by_name(_DEFAULT_CATEGORY_NAME)
            if default is None:
                raise ValueError(f"Default shopping category {_DEFAULT_CATEGORY_NAME!r} is missing")
            data = data.model_copy(update={"category_id": default.id})
        product = await self._repo.create(data)
        logger.info("Shopping product created: id=%d name=%r", product.id, product.name)
        return ShoppingProductRead.model_validate(product)

    async def update(self, product_id: int, data: ShoppingProductUpdate) -> ShoppingProductRead | None:
        product = await self._repo.update(product_id, data)
        if product is None:
            logger.debug("Shopping product update: id=%d not found", product_id)
            return None
        logger.info(
            "Shopping product updated: id=%d fields=%s", product_id, list(data.model_dump(exclude_unset=True))
        )
        return ShoppingProductRead.model_validate(product)

    async def delete(self, product_id: int) -> bool:
        product = await self._repo.get(product_id)
        if product is None:
            logger.debug("Shopping product delete: id=%d not found", product_id)
            return False
        name = product.name
        if await self._repo.has_pending(product_id):
            raise ShoppingProductBlockedError(f"{name!r} is on the shopping list; remove that entry first")
        await self._repo.delete(product_id)
        logger.info("Shopping product deleted: id=%d name=%r", product_id, name)
        return True

    async def merge(self, source_id: int, into_id: int) -> ShoppingProductRead | None:
        """Fold one product into another: its entries and history move, the source is deleted."""
        if source_id == into_id:
            raise ShoppingProductBlockedError("A product cannot be merged into itself")
        source = await self._repo.get(source_id)
        target = await self._repo.get(into_id)
        if source is None or target is None:
            return None
        source_name, target_name = source.name, target.name
        if await self._repo.has_pending(source_id) and await self._repo.has_pending(into_id):
            raise ShoppingProductBlockedError(
                f"Both {source_name!r} and {target_name!r} are on the shopping list; remove one entry first"
            )
        await self._repo.repoint_items(source_id, into_id)
        await self._repo.delete(source_id)
        logger.info("Shopping products merged: source_id=%d into_id=%d", source_id, into_id)
        merged = await self._repo.get(into_id)
        return ShoppingProductRead.model_validate(merged)
