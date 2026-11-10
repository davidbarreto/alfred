import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.tags.repository import TravelTagRepository
from app.features.travel.tags.schemas import TravelTagRead, TravelTagUpdate, TravelTagUsage

logger = logging.getLogger(__name__)


class TravelTagNameTakenError(Exception):
    """Another travel tag already uses that name (case-insensitive)."""


class TravelTagService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = TravelTagRepository(session)

    async def get_tags(self) -> list[TravelTagUsage]:
        rows = await self._repo.get_tags_with_usage()
        return [TravelTagUsage(id=tag.id, name=tag.name, trip_count=trips, place_count=places) for tag, trips, places in rows]

    async def rename_tag(self, tag_id: int, data: TravelTagUpdate) -> TravelTagRead | None:
        existing = await self._repo.get_tag_by_name(data.name)
        if existing is not None and existing.id != tag_id:
            raise TravelTagNameTakenError(data.name)
        try:
            tag = await self._repo.rename_tag(tag_id, data.name)
        except IntegrityError as exc:
            await self._session.rollback()
            raise TravelTagNameTakenError(data.name) from exc
        if tag is None:
            logger.debug("Travel tag rename: id=%d not found", tag_id)
            return None
        logger.info("Travel tag renamed: id=%d name=%r", tag_id, tag.name)
        return TravelTagRead.model_validate(tag)

    async def delete_tag(self, tag_id: int) -> bool:
        deleted = await self._repo.delete_tag(tag_id)
        if deleted:
            logger.info("Travel tag deleted: id=%d", tag_id)
        return deleted
