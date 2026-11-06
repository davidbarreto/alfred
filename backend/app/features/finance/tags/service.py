import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.budgets.repository import BudgetTargetRepository
from app.features.finance.tags.repository import TagRepository
from app.features.finance.tags.schemas import TagCreate, TagRead, TagUpdate

logger = logging.getLogger(__name__)


class TagDeletionBlockedError(Exception):
    """Raised when a tag can't be deleted because it still has an open budget target."""

    def __init__(self, tag_id: int) -> None:
        self.tag_id = tag_id
        super().__init__(f"Tag {tag_id} cannot be deleted: it has an open budget target")


class TagNameConflictError(Exception):
    """Raised when a tag name is already taken, ignoring case ("travel" vs "Travel")."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"A tag named {name!r} already exists")


class TagService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = TagRepository(session)
        self._budget_repo = BudgetTargetRepository(session)

    async def get(self, tag_id: int) -> TagRead | None:
        tag = await self._repo.get_tag(tag_id)
        if tag is None:
            return None
        return TagRead.model_validate(tag)

    async def list(self) -> list[TagRead]:
        tags = await self._repo.get_tags()
        return [TagRead.model_validate(t) for t in tags]

    async def create(self, data: TagCreate) -> TagRead:
        if await self._repo.get_tag_by_name(data.name) is not None:
            logger.warning("Tag create blocked: name=%r already exists", data.name)
            raise TagNameConflictError(data.name)
        tag = await self._repo.create_tag(data)
        logger.info("Tag created: id=%d name=%r", tag.id, data.name)
        return TagRead.model_validate(tag)

    async def update(self, tag_id: int, data: TagUpdate) -> TagRead | None:
        if data.name is not None and await self._repo.get_tag_by_name(data.name, exclude_id=tag_id) is not None:
            logger.warning("Tag update blocked: id=%d name=%r already exists", tag_id, data.name)
            raise TagNameConflictError(data.name)
        tag = await self._repo.update_tag(tag_id, data)
        if tag is None:
            logger.debug("Tag update: id=%d not found", tag_id)
            return None
        logger.info("Tag updated: id=%d fields=%s", tag_id, list(data.model_dump(exclude_unset=True).keys()))
        return TagRead.model_validate(tag)

    async def delete(self, tag_id: int) -> bool:
        if await self._budget_repo.has_open_tag_target(tag_id):
            logger.warning("Tag delete blocked: id=%d has an open budget target", tag_id)
            raise TagDeletionBlockedError(tag_id)
        deleted = await self._repo.delete_tag(tag_id)
        if deleted:
            logger.info("Tag deleted: id=%d", tag_id)
        else:
            logger.debug("Tag delete: id=%d not found", tag_id)
        return deleted
