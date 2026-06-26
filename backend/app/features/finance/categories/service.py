import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)

logger = logging.getLogger(__name__)


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
        logger.info("Category created: id=%d name=%r", category.id, data.name)
        return CategoryRead.model_validate(category)

    async def update(self, category_id: int, data: CategoryUpdate) -> CategoryRead | None:
        category = await self._repo.update(category_id, data)
        if category is None:
            logger.debug("Category update: id=%d not found", category_id)
            return None
        logger.info("Category updated: id=%d fields=%s", category_id, list(data.model_dump(exclude_unset=True).keys()))
        return CategoryRead.model_validate(category)

    async def delete(self, category_id: int) -> bool:
        deleted = await self._repo.delete(category_id)
        if deleted:
            logger.info("Category deleted: id=%d", category_id)
        else:
            logger.debug("Category delete: id=%d not found", category_id)
        return deleted
