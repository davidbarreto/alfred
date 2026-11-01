from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.features.organizer.shopping.errors import ShoppingItemAlreadyPendingError
from app.features.organizer.shopping.schemas import (
    FrequentItemFilters,
    RecurrenceItemCreate,
    RecurrenceItemUpdate,
    ShoppingItemCreate,
    ShoppingItemFilters,
    ShoppingItemUpdate,
    WishlistItemCreate,
    WishlistItemFilters,
    WishlistItemUpdate,
)
from app.features.organizer.shopping.tables import RecurrenceItem, ShoppingItem, WishlistItem
from app.features.organizer.shopping_products.tables import ShoppingProduct


def _items_query():
    return (
        select(ShoppingItem)
        .join(ShoppingItem.product)
        .options(contains_eager(ShoppingItem.product))
        .where(ShoppingItem.deleted_at.is_(None))
    )


class ShoppingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> ShoppingItem | None:
        result = await self._session.execute(_items_query().where(ShoppingItem.id == item_id))
        return result.scalars().first()

    async def get_pending_by_product(self, product_id: int) -> ShoppingItem | None:
        result = await self._session.execute(
            _items_query().where(ShoppingItem.product_id == product_id, ShoppingItem.status == "pending")
        )
        return result.scalars().first()

    async def list(self, filters: ShoppingItemFilters) -> list[ShoppingItem]:
        query = _items_query()
        if filters.status != "all":
            query = query.where(ShoppingItem.status == filters.status)
        if filters.category_id is not None:
            query = query.where(ShoppingProduct.category_id == filters.category_id)
        if filters.priority != "all":
            query = query.where(ShoppingItem.priority == filters.priority)
        query = query.order_by(ShoppingItem.created_at.asc()).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, product_id: int, data: ShoppingItemCreate) -> ShoppingItem:
        item = ShoppingItem(product_id=product_id, **data.model_dump(exclude={"name", "category_id"}))
        self._session.add(item)
        await self._commit_pending_safe(data.name)
        created = await self.get(item.id)
        assert created is not None
        return created

    async def update(self, item_id: int, data: ShoppingItemUpdate) -> ShoppingItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        name = item.name
        fields = data.model_dump(exclude_unset=True, exclude={"name", "category_id"})
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem).where(ShoppingItem.id == item_id).values(**fields)
        )
        await self._commit_pending_safe(name)
        self._session.expire_all()
        return await self.get(item_id)

    async def _commit_pending_safe(self, name: str) -> None:
        """Commit, turning a violation of the one-pending-entry-per-product index into a domain error."""
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            if "uq_shopping_items_pending_product" in str(exc):
                raise ShoppingItemAlreadyPendingError(name) from exc
            raise

    async def delete(self, item_id: int) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem)
            .where(ShoppingItem.id == item_id)
            .values(deleted_at=now, updated_at=now)
        )
        await self._session.commit()

    async def mark_bought(self, item_id: int) -> ShoppingItem | None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem)
            .where(ShoppingItem.id == item_id)
            .values(status="bought", last_bought_at=now, updated_at=now)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def mark_skipped(self, item_id: int) -> ShoppingItem | None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem)
            .where(ShoppingItem.id == item_id)
            .values(status="skipped", updated_at=now)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def get_frequent(self, filters: FrequentItemFilters) -> list[Row]:
        """Most-bought products with no pending entry; the exclusion runs before the limit."""
        pending_products = select(ShoppingItem.product_id).where(
            ShoppingItem.status == "pending", ShoppingItem.deleted_at.is_(None)
        )
        query = (
            select(
                ShoppingProduct.id.label("product_id"),
                ShoppingProduct.name,
                ShoppingProduct.category_id,
                ShoppingProduct.default_unit,
                func.count().label("purchase_count"),
                func.max(ShoppingItem.last_bought_at).label("last_bought_at"),
            )
            .join(ShoppingItem, ShoppingItem.product_id == ShoppingProduct.id)
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingProduct.deleted_at.is_(None),
                ShoppingProduct.id.notin_(pending_products),
            )
            .group_by(ShoppingProduct.id)
        )
        if filters.category_id is not None:
            query = query.where(ShoppingProduct.category_id == filters.category_id)
        query = query.order_by(func.count().desc(), func.max(ShoppingItem.last_bought_at).desc()).limit(
            filters.limit
        )
        result = await self._session.execute(query)
        return list(result.all())

    async def get_purchases_by_category(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingProduct.category_id, func.count().label("purchase_count"))
            .select_from(ShoppingItem)
            .join(ShoppingProduct, ShoppingItem.product_id == ShoppingProduct.id)
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingProduct.category_id.is_not(None),
            )
            .group_by(ShoppingProduct.category_id)
            .order_by(func.count().desc())
        )
        return list(result.all())

    async def get_bought_history(self, category_id: int | None = None) -> list[Row]:
        """One row per bought entry of a live product, ordered for per-product grouping."""
        query = (
            select(
                ShoppingItem.product_id,
                ShoppingProduct.name,
                ShoppingProduct.category_id,
                ShoppingItem.last_bought_at,
            )
            .join(ShoppingProduct, ShoppingItem.product_id == ShoppingProduct.id)
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.last_bought_at.is_not(None),
                ShoppingProduct.deleted_at.is_(None),
            )
            .order_by(ShoppingItem.product_id, ShoppingItem.last_bought_at)
        )
        if category_id is not None:
            query = query.where(ShoppingProduct.category_id == category_id)
        result = await self._session.execute(query)
        return list(result.all())

    async def get_purchases_by_month(self, months: int) -> list[Row]:
        since = datetime.now(timezone.utc) - timedelta(days=30 * months)
        month = func.to_char(ShoppingItem.last_bought_at, "YYYY-MM").label("month")
        result = await self._session.execute(
            select(month, func.count().label("purchase_count"))
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.last_bought_at.is_not(None),
                ShoppingItem.last_bought_at >= since,
            )
            .group_by(month)
            .order_by(month)
        )
        return list(result.all())

    async def get_priority_counts(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingItem.priority, func.count().label("item_count"))
            .where(ShoppingItem.deleted_at.is_(None))
            .group_by(ShoppingItem.priority)
        )
        return list(result.all())

    async def get_purchases_by_store(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingItem.store, func.count().label("purchase_count"))
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.store.is_not(None),
            )
            .group_by(ShoppingItem.store)
            .order_by(func.count().desc())
        )
        return list(result.all())


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> WishlistItem | None:
        result = await self._session.execute(
            select(WishlistItem).where(
                WishlistItem.id == item_id,
                WishlistItem.deleted_at.is_(None),
                WishlistItem.promoted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list(self, filters: WishlistItemFilters) -> list[WishlistItem]:
        query = select(WishlistItem).where(
            WishlistItem.deleted_at.is_(None),
            WishlistItem.promoted_at.is_(None),
        )
        if filters.category_id is not None:
            query = query.where(WishlistItem.category_id == filters.category_id)
        query = query.order_by(WishlistItem.created_at.asc()).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: WishlistItemCreate) -> WishlistItem:
        item = WishlistItem(**data.model_dump())
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def update(self, item_id: int, data: WishlistItemUpdate) -> WishlistItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem).where(WishlistItem.id == item_id).values(**fields)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def delete(self, item_id: int) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem)
            .where(WishlistItem.id == item_id)
            .values(deleted_at=now, updated_at=now, category_id=None)
        )
        await self._session.commit()

    async def promote(self, item_id: int) -> WishlistItem | None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem).where(WishlistItem.id == item_id).values(promoted_at=now, updated_at=now)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def get_purchases_by_category(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingProduct.category_id, func.count().label("purchase_count"))
            .select_from(ShoppingItem)
            .join(ShoppingProduct, ShoppingItem.product_id == ShoppingProduct.id)
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingProduct.category_id.is_not(None),
            )
            .group_by(ShoppingProduct.category_id)
            .order_by(func.count().desc())
        )
        return list(result.all())

    async def get_purchases_by_month(self, months: int) -> list[Row]:
        since = datetime.now(timezone.utc) - timedelta(days=30 * months)
        month = func.to_char(ShoppingItem.last_bought_at, "YYYY-MM").label("month")
        result = await self._session.execute(
            select(month, func.count().label("purchase_count"))
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.last_bought_at.is_not(None),
                ShoppingItem.last_bought_at >= since,
            )
            .group_by(month)
            .order_by(month)
        )
        return list(result.all())

    async def get_priority_counts(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingItem.priority, func.count().label("item_count"))
            .where(ShoppingItem.deleted_at.is_(None))
            .group_by(ShoppingItem.priority)
        )
        return list(result.all())

    async def get_purchases_by_store(self) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingItem.store, func.count().label("purchase_count"))
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.store.is_not(None),
            )
            .group_by(ShoppingItem.store)
            .order_by(func.count().desc())
        )
        return list(result.all())


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> WishlistItem | None:
        result = await self._session.execute(
            select(WishlistItem).where(
                WishlistItem.id == item_id,
                WishlistItem.deleted_at.is_(None),
                WishlistItem.promoted_at.is_(None),
            )
        )
        return result.scalars().first()

    async def list(self, filters: WishlistItemFilters) -> list[WishlistItem]:
        query = select(WishlistItem).where(
            WishlistItem.deleted_at.is_(None),
            WishlistItem.promoted_at.is_(None),
        )
        if filters.category_id is not None:
            query = query.where(WishlistItem.category_id == filters.category_id)
        query = query.order_by(WishlistItem.created_at.asc()).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: WishlistItemCreate) -> WishlistItem:
        item = WishlistItem(**data.model_dump())
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def update(self, item_id: int, data: WishlistItemUpdate) -> WishlistItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem).where(WishlistItem.id == item_id).values(**fields)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def delete(self, item_id: int) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem)
            .where(WishlistItem.id == item_id)
            .values(deleted_at=now, updated_at=now, category_id=None)
        )
        await self._session.commit()

    async def promote(self, item_id: int) -> WishlistItem | None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(WishlistItem).where(WishlistItem.id == item_id).values(promoted_at=now, updated_at=now)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(WishlistItem).where(WishlistItem.category_id == category_id)
        )
        return result.scalar_one()

    async def search_names(self, query: str, limit: int) -> list[Row]:
        result = await self._session.execute(
            select(WishlistItem.name, WishlistItem.category_id, WishlistItem.updated_at)
            .where(WishlistItem.deleted_at.is_(None), WishlistItem.name.ilike(f"%{query}%"))
            .order_by(WishlistItem.updated_at.desc())
            .limit(limit)
        )
        return list(result.all())


class RecurrenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> RecurrenceItem | None:
        result = await self._session.execute(
            select(RecurrenceItem).where(RecurrenceItem.id == item_id)
        )
        return result.scalars().first()

    async def list(self, active_only: bool = True) -> list[RecurrenceItem]:
        query = select(RecurrenceItem)
        if active_only:
            query = query.where(RecurrenceItem.active.is_(True))
        query = query.order_by(RecurrenceItem.name.asc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: RecurrenceItemCreate) -> RecurrenceItem:
        item = RecurrenceItem(**data.model_dump())
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def update(self, item_id: int, data: RecurrenceItemUpdate) -> RecurrenceItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            update(RecurrenceItem).where(RecurrenceItem.id == item_id).values(**fields)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def delete(self, item_id: int) -> None:
        await self._session.execute(delete(RecurrenceItem).where(RecurrenceItem.id == item_id))
        await self._session.commit()

    async def mark_added(self, item_id: int) -> RecurrenceItem | None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(RecurrenceItem).where(RecurrenceItem.id == item_id).values(last_added_at=now, updated_at=now)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(RecurrenceItem).where(RecurrenceItem.category_id == category_id)
        )
        return result.scalar_one()

    async def search_names(self, query: str, limit: int) -> list[Row]:
        result = await self._session.execute(
            select(RecurrenceItem.name, RecurrenceItem.category_id, RecurrenceItem.updated_at)
            .where(RecurrenceItem.name.ilike(f"%{query}%"))
            .order_by(RecurrenceItem.updated_at.desc())
            .limit(limit)
        )
        return list(result.all())
