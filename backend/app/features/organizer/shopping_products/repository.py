from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import exists, func, select, update
from sqlalchemy.engine import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.errors import ShoppingProductNameTakenError
from app.features.organizer.shopping.tables import ShoppingItem
from app.features.organizer.shopping_products.schemas import (
    ShoppingProductCreate,
    ShoppingProductFilters,
    ShoppingProductUpdate,
)
from app.features.organizer.shopping_products.tables import ShoppingProduct


class ShoppingProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, product_id: int) -> ShoppingProduct | None:
        result = await self._session.execute(
            select(ShoppingProduct).where(ShoppingProduct.id == product_id, ShoppingProduct.deleted_at.is_(None))
        )
        return result.scalars().first()

    async def get_by_name(self, name: str) -> ShoppingProduct | None:
        result = await self._session.execute(
            select(ShoppingProduct).where(
                func.lower(ShoppingProduct.name) == name.strip().lower(), ShoppingProduct.deleted_at.is_(None)
            )
        )
        return result.scalars().first()

    async def list(self, filters: ShoppingProductFilters) -> list[Row]:
        """Rows of (ShoppingProduct, purchase_count, pending)."""
        purchases = (
            select(func.count())
            .where(
                ShoppingItem.product_id == ShoppingProduct.id,
                ShoppingItem.status == "bought",
                ShoppingItem.deleted_at.is_(None),
            )
            .scalar_subquery()
        )
        pending = exists().where(
            ShoppingItem.product_id == ShoppingProduct.id,
            ShoppingItem.status == "pending",
            ShoppingItem.deleted_at.is_(None),
        )
        query = select(ShoppingProduct, purchases.label("purchase_count"), pending.label("pending")).where(
            ShoppingProduct.deleted_at.is_(None)
        )
        if filters.q:
            query = query.where(ShoppingProduct.name.ilike(f"%{filters.q}%"))
        if filters.category_id is not None:
            query = query.where(ShoppingProduct.category_id == filters.category_id)
        query = query.order_by(func.lower(ShoppingProduct.name)).limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(query)
        return list(result.all())

    async def create(self, data: ShoppingProductCreate) -> ShoppingProduct:
        product = ShoppingProduct(**data.model_dump())
        self._session.add(product)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ShoppingProductNameTakenError(data.name) from exc
        await self._session.refresh(product)
        return product

    async def update(self, product_id: int, data: ShoppingProductUpdate) -> ShoppingProduct | None:
        if await self.get(product_id) is None:
            return None
        fields = data.model_dump(exclude_unset=True)
        fields["updated_at"] = datetime.now(timezone.utc)
        try:
            await self._session.execute(
                update(ShoppingProduct).where(ShoppingProduct.id == product_id).values(**fields)
            )
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ShoppingProductNameTakenError(fields.get("name", "")) from exc
        self._session.expire_all()
        return await self.get(product_id)

    async def delete(self, product_id: int) -> None:
        now = datetime.now(timezone.utc)
        await self._session.execute(
            update(ShoppingProduct)
            .where(ShoppingProduct.id == product_id)
            .values(deleted_at=now, updated_at=now, category_id=None)
        )
        await self._session.commit()

    async def has_pending(self, product_id: int) -> bool:
        result = await self._session.execute(
            select(
                exists().where(
                    ShoppingItem.product_id == product_id,
                    ShoppingItem.status == "pending",
                    ShoppingItem.deleted_at.is_(None),
                )
            )
        )
        return bool(result.scalar_one())

    async def repoint_items(self, source_id: int, target_id: int) -> None:
        """Move every list entry of one product to another (the caller checks pending clashes)."""
        await self._session.execute(
            update(ShoppingItem)
            .where(ShoppingItem.product_id == source_id)
            .values(product_id=target_id, updated_at=datetime.now(timezone.utc))
        )
        await self._session.commit()

    async def count_by_category(self, category_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(ShoppingProduct).where(ShoppingProduct.category_id == category_id)
        )
        return result.scalar_one()

    async def search_names(self, query: str, limit: int) -> list[Row]:
        result = await self._session.execute(
            select(
                ShoppingProduct.name,
                ShoppingProduct.category_id,
                ShoppingProduct.default_unit,
                ShoppingProduct.updated_at,
            )
            .where(ShoppingProduct.deleted_at.is_(None), ShoppingProduct.name.ilike(f"%{query}%"))
            .order_by(ShoppingProduct.updated_at.desc())
            .limit(limit)
        )
        return list(result.all())
