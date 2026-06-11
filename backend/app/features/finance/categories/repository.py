from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.categories.tables import Category
from app.features.finance.categories.schemas import CategoryCreate, CategoryUpdate


class CategoryRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, category_id: int) -> Category | None:
        result = await self._session.execute(
            select(Category).where(Category.id == category_id)
        )
        return result.scalars().first()

    async def list(self) -> list[Category]:
        result = await self._session.execute(select(Category).order_by(Category.name))
        return list(result.scalars().all())

    async def create(self, data: CategoryCreate) -> Category:
        category = Category(**data.model_dump())
        self._session.add(category)
        await self._session.commit()
        await self._session.refresh(category)
        return category

    async def update(self, category_id: int, data: CategoryUpdate) -> Category | None:
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
        await self._session.commit()
        return True
