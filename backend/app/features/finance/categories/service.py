import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.repository import BudgetTargetRepository
from app.features.finance.categories.repository import CategoryRepository
from app.features.finance.categories.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
)

logger = logging.getLogger(__name__)


class CategoryDeletionBlockedError(Exception):
    """Raised when a category can't be deleted because budget targets still reference it
    (RESTRICT, not CASCADE/SET NULL -- unlike transactions, which fall back to uncategorized,
    a budget target has no meaningful value without its category)."""

    def __init__(self, category_id: int, budget_count: int) -> None:
        self.category_id = category_id
        self.budget_count = budget_count
        super().__init__(
            f"Category {category_id} cannot be deleted: {budget_count} budget target(s) reference it"
        )


class CategoryService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = CategoryRepository(session)
        self._budget_repo = BudgetTargetRepository(session)

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
        category = await self._repo.get(category_id)
        if category is None:
            logger.debug("Category delete: id=%d not found", category_id)
            return False
        try:
            await self._repo.delete(category_id)
        except IntegrityError:
            budget_count = await self._budget_repo.count_by_category(category_id)
            logger.warning(
                "Category delete blocked: id=%d name=%r budget_count=%d",
                category_id, category.name, budget_count,
            )
            raise CategoryDeletionBlockedError(category_id, budget_count)
        logger.info("Category deleted: id=%d", category_id)
        return True
