from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping_categories.schemas import ShoppingCategoryCreate, ShoppingCategoryUpdate
from app.features.organizer.shopping_categories.tables import ShoppingCategory


class ShoppingCategoryRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, category_id: int) -> ShoppingCategory | None:
        result = await self._session.execute(
            select(ShoppingCategory).where(ShoppingCategory.id == category_id)
        )
        return result.scalars().first()

    async def get_by_name(self, name: str) -> ShoppingCategory | None:
        result = await self._session.execute(
            select(ShoppingCategory).where(func.lower(ShoppingCategory.name) == name.lower())
        )
        return result.scalars().first()

    async def list(self) -> list[ShoppingCategory]:
        result = await self._session.execute(select(ShoppingCategory).order_by(ShoppingCategory.name))
        return list(result.scalars().all())

    async def create(self, data: ShoppingCategoryCreate) -> ShoppingCategory:
        category = ShoppingCategory(**data.model_dump())
        self._session.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def update(self, category_id: int, data: ShoppingCategoryUpdate) -> ShoppingCategory | None:
        category = await self.get(category_id)
        if category is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(category, field, value)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def delete(self, category_id: int) -> bool:
        category = await self.get(category_id)
        if category is None:
            return False
        await self._session.delete(category)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise
        return True
