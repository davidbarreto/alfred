import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.shopping.repository import (
    RecurrenceRepository,
    ShoppingRepository,
    WishlistRepository,
)
from app.features.organizer.shopping_categories.repository import ShoppingCategoryRepository
from app.features.organizer.shopping_categories.schemas import (
    ShoppingCategoryCreate,
    ShoppingCategoryRead,
    ShoppingCategoryUpdate,
)

logger = logging.getLogger(__name__)


class ShoppingCategoryDeletionBlockedError(Exception):
    """Raised when a shopping category can't be deleted because shopping, wishlist, or
    recurrence items still reference it (all RESTRICT, not CASCADE, so a delete can never
    silently orphan or destroy shopping data)."""

    def __init__(self, category_id: int, shopping_count: int, wishlist_count: int, recurrence_count: int) -> None:
        self.category_id = category_id
        self.shopping_count = shopping_count
        self.wishlist_count = wishlist_count
        self.recurrence_count = recurrence_count
        super().__init__(
            f"Category {category_id} cannot be deleted: {shopping_count} shopping item(s), "
            f"{wishlist_count} wishlist item(s), {recurrence_count} recurrence item(s) reference it"
        )


class ShoppingCategoryService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = ShoppingCategoryRepository(session)
        self._shopping_repo = ShoppingRepository(session)
        self._wishlist_repo = WishlistRepository(session)
        self._recurrence_repo = RecurrenceRepository(session)

    async def get(self, category_id: int) -> ShoppingCategoryRead | None:
        category = await self._repo.get(category_id)
        if category is None:
            return None
        return ShoppingCategoryRead.model_validate(category)

    async def list(self) -> list[ShoppingCategoryRead]:
        categories = await self._repo.list()
        return [ShoppingCategoryRead.model_validate(c) for c in categories]

    async def create(self, data: ShoppingCategoryCreate) -> ShoppingCategoryRead:
        category = await self._repo.create(data)
        logger.info("Shopping category created: id=%d name=%r", category.id, data.name)
        return ShoppingCategoryRead.model_validate(category)

    async def update(self, category_id: int, data: ShoppingCategoryUpdate) -> ShoppingCategoryRead | None:
        category = await self._repo.update(category_id, data)
        if category is None:
            logger.debug("Shopping category update: id=%d not found", category_id)
            return None
        logger.info(
            "Shopping category updated: id=%d fields=%s", category_id, list(data.model_dump(exclude_unset=True).keys())
        )
        return ShoppingCategoryRead.model_validate(category)

    async def delete(self, category_id: int) -> bool:
        category = await self._repo.get(category_id)
        if category is None:
            logger.debug("Shopping category delete: id=%d not found", category_id)
            return False
        try:
            await self._repo.delete(category_id)
        except IntegrityError:
            shopping_count = await self._shopping_repo.count_by_category(category_id)
            wishlist_count = await self._wishlist_repo.count_by_category(category_id)
            recurrence_count = await self._recurrence_repo.count_by_category(category_id)
            logger.warning(
                "Shopping category delete blocked: id=%d name=%r shopping=%d wishlist=%d recurrence=%d",
                category_id, category.name, shopping_count, wishlist_count, recurrence_count,
            )
            raise ShoppingCategoryDeletionBlockedError(category_id, shopping_count, wishlist_count, recurrence_count)
        logger.info("Shopping category deleted: id=%d name=%r", category_id, category.name)
        return True
