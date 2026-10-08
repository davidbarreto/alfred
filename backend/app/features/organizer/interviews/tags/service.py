import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.tags.repository import InterviewTagRepository
from app.features.organizer.interviews.tags.schemas import InterviewTagRead, InterviewTagUpdate, InterviewTagUsage

logger = logging.getLogger(__name__)


class InterviewTagNameTakenError(Exception):
    """Another tag already uses that name (case-insensitive)."""


class InterviewTagService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = InterviewTagRepository(session)

    async def get_tags(self) -> list[InterviewTagUsage]:
        rows = await self._repo.get_tags_with_usage()
        return [
            InterviewTagUsage(id=tag.id, name=tag.name, story_count=stories, question_count=questions)
            for tag, stories, questions in rows
        ]

    async def rename_tag(self, tag_id: int, data: InterviewTagUpdate) -> InterviewTagRead | None:
        existing = await self._repo.get_tag_by_name(data.name)
        if existing is not None and existing.id != tag_id:
            raise InterviewTagNameTakenError(data.name)
        try:
            tag = await self._repo.rename_tag(tag_id, data.name)
        except IntegrityError as exc:
            await self._session.rollback()
            raise InterviewTagNameTakenError(data.name) from exc
        if tag is None:
            logger.debug("Interview tag rename: id=%d not found", tag_id)
            return None
        logger.info("Interview tag renamed: id=%d name=%r", tag_id, tag.name)
        return InterviewTagRead.model_validate(tag)

    async def delete_tag(self, tag_id: int) -> bool:
        deleted = await self._repo.delete_tag(tag_id)
        if deleted:
            logger.info("Interview tag deleted: id=%d", tag_id)
        return deleted
