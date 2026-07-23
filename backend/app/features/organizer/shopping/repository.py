from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

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


class ShoppingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> ShoppingItem | None:
        result = await self._session.execute(
            select(ShoppingItem).where(ShoppingItem.id == item_id, ShoppingItem.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def list(self, filters: ShoppingItemFilters) -> list[ShoppingItem]:
        query = select(ShoppingItem).where(ShoppingItem.deleted_at.is_(None))
        if filters.status != "all":
            query = query.where(ShoppingItem.status == filters.status)
        if filters.category_id is not None:
            query = query.where(ShoppingItem.category_id == filters.category_id)
        if filters.priority != "all":
            query = query.where(ShoppingItem.priority == filters.priority)
        query = query.order_by(ShoppingItem.created_at.asc()).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: ShoppingItemCreate) -> ShoppingItem:
        item = ShoppingItem(**data.model_dump())
        self._session.add(item)
        await self._session.commit()
        await self._session.refresh(item)
        return item

    async def update(self, item_id: int, data: ShoppingItemUpdate) -> ShoppingItem | None:
        item = await self.get(item_id)
        if item is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem).where(ShoppingItem.id == item_id).values(**fields)
        )
        await self._session.commit()
        return await self.get(item_id)

    async def delete(self, item_id: int) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingItem).where(ShoppingItem.id == item_id).values(deleted_at=now, updated_at=now)
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
        pending_names = select(ShoppingItem.name).where(
            ShoppingItem.status == "pending", ShoppingItem.deleted_at.is_(None)
        )
        query = (
            select(
                ShoppingItem.name,
                ShoppingItem.category_id,
                func.count().label("purchase_count"),
                func.max(ShoppingItem.last_bought_at).label("last_bought_at"),
            )
            .where(
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
                ShoppingItem.name.notin_(pending_names),
            )
            .group_by(ShoppingItem.name, ShoppingItem.category_id)
        )
        if filters.category_id is not None:
            query = query.where(ShoppingItem.category_id == filters.category_id)
        query = query.order_by(func.count().desc(), func.max(ShoppingItem.last_bought_at).desc()).limit(
            filters.limit
        )
        result = await self._session.execute(query)
        return list(result.all())

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(ShoppingItem).where(ShoppingItem.category_id == category_id)
        )
        return result.scalar_one()

    async def search_names(self, query: str, limit: int) -> list[Row]:
        result = await self._session.execute(
            select(ShoppingItem.name, ShoppingItem.category_id, ShoppingItem.updated_at)
            .where(ShoppingItem.deleted_at.is_(None), ShoppingItem.name.ilike(f"%{query}%"))
            .order_by(ShoppingItem.updated_at.desc())
            .limit(limit)
        )
        return list(result.all())


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> WishlistItem | None:
        result = await self._session.execute(
            select(WishlistItem).where(WishlistItem.id == item_id)
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
            update(WishlistItem).where(WishlistItem.id == item_id).values(deleted_at=now, updated_at=now)
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
