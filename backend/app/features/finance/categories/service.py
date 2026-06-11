from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)


class CategoryService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = CategoryRepository(session)

    async def get(self, category_id: int) -> CategoryRead | None:
        category = await self._repo.get(category_id)
        if category is None:
            return None
        return CategoryRead.model_validate(category)

    async def list(self) -> list[CategoryRead]:
        categories = await self._repo.list()
        return [CategoryRead.model_validate(c) for c in categories]

    async def create(self, data: CategoryCreate) -> CategoryRead:
        category = await self._repo.create(data)
        return CategoryRead.model_validate(category)

    async def update(self, category_id: int, data: CategoryUpdate) -> CategoryRead | None:
        category = await self._repo.update(category_id, data)
        if category is None:
            return None
        return CategoryRead.model_validate(category)

    async def delete(self, category_id: int) -> bool:
        return await self._repo.delete(category_id)
