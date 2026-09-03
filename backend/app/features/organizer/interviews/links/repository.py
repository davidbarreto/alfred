from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.links.schemas import InterviewLinkCreate
from app.features.organizer.interviews.links.tables import InterviewLink


class InterviewLinkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_link(self, link_id: int) -> InterviewLink | None:
        result = await self._session.execute(select(InterviewLink).where(InterviewLink.id == link_id))
        return result.scalars().first()

    async def get_links(self, process_id: int) -> list[InterviewLink]:
        result = await self._session.execute(
            select(InterviewLink)
            .where(InterviewLink.process_id == process_id)
            .order_by(InterviewLink.created_at)
        )
        return list(result.scalars().all())

    async def create_link(self, data: InterviewLinkCreate) -> InterviewLink:
        link = InterviewLink(**data.model_dump())
        self._session.add(link)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def delete_link(self, link_id: int) -> None:
        link = await self.get_link(link_id)
        if link is not None:
            await self._session.delete(link)
            await self._session.commit()
