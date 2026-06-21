from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.schemas import (
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
            select(ShoppingItem).where(ShoppingItem.id == item_id)
        )
        return result.scalars().first()

    async def list(self, filters: ShoppingItemFilters) -> list[ShoppingItem]:
        query = select(ShoppingItem)
        if filters.status != "all":
            query = query.where(ShoppingItem.status == filters.status)
        if filters.category != "all":
            query = query.where(ShoppingItem.category == filters.category)
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
        await self._session.execute(delete(ShoppingItem).where(ShoppingItem.id == item_id))
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


class WishlistRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, item_id: int) -> WishlistItem | None:
        result = await self._session.execute(
            select(WishlistItem).where(WishlistItem.id == item_id)
        )
        return result.scalars().first()

    async def list(self, filters: WishlistItemFilters) -> list[WishlistItem]:
        query = select(WishlistItem)
        if filters.category != "all":
            query = query.where(WishlistItem.category == filters.category)
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
        await self._session.execute(delete(WishlistItem).where(WishlistItem.id == item_id))
        await self._session.commit()


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
