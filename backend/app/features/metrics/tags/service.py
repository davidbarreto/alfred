import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.tags.repository import MetricTagRepository
from app.features.metrics.tags.schemas import MetricTagRead, MetricTagUpdate, MetricTagUsage

logger = logging.getLogger(__name__)


class MetricTagNameTakenError(Exception):
    """Another tag already uses that name (case-insensitive)."""


class MetricTagInUseError(Exception):
    """The tag is still attached to entries, so it can't be deleted."""

    def __init__(self, entry_count: int):
        super().__init__(f"Tag is used by {entry_count} entries")
        self.entry_count = entry_count


class MetricTagService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = MetricTagRepository(session)

    async def get_tags(self) -> list[MetricTagUsage]:
        rows = await self._repo.get_tags_with_usage()
        return [MetricTagUsage(id=tag.id, name=tag.name, entry_count=n) for tag, n in rows]

    async def rename_tag(self, tag_id: int, data: MetricTagUpdate) -> MetricTagRead | None:
        existing = await self._repo.get_tag_by_name(data.name)
        if existing is not None and existing.id != tag_id:
            raise MetricTagNameTakenError(data.name)
        try:
            tag = await self._repo.rename_tag(tag_id, data.name)
        except IntegrityError as exc:
            await self._session.rollback()
            raise MetricTagNameTakenError(data.name) from exc
        if tag is None:
            logger.debug("Metric tag rename: id=%d not found", tag_id)
            return None
        logger.info("Metric tag renamed: id=%d name=%r", tag_id, tag.name)
        return MetricTagRead.model_validate(tag)

    async def delete_tag(self, tag_id: int) -> bool:
        usage = await self._repo.count_usage(tag_id)
        if usage:
            raise MetricTagInUseError(usage)
        deleted = await self._repo.delete_tag(tag_id)
        if deleted:
            logger.info("Metric tag deleted: id=%d", tag_id)
        return deleted
