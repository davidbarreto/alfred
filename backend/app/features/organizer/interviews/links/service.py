from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.links.repository import InterviewLinkRepository
from app.features.organizer.interviews.links.schemas import InterviewLinkCreate, InterviewLinkRead

logger = logging.getLogger(__name__)


class InterviewLinkService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = InterviewLinkRepository(session)

    async def get_links(self, process_id: int) -> list[InterviewLinkRead]:
        links = await self._repo.get_links(process_id)
        return [InterviewLinkRead.model_validate(link) for link in links]

    async def create_link(self, data: InterviewLinkCreate) -> InterviewLinkRead:
        link = await self._repo.create_link(data)
        logger.info("Interview link created: id=%d process_id=%d", link.id, link.process_id)
        return InterviewLinkRead.model_validate(link)

    async def delete_link(self, link_id: int) -> None:
        await self._repo.delete_link(link_id)
        logger.info("Interview link deleted: id=%d", link_id)
