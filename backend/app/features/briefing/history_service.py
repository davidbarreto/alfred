from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.repository import BriefingRepository
from app.features.briefing.schemas import BriefingHistoryItem


class BriefingHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = BriefingRepository(session)

    async def list(self, briefing_type: str | None, limit: int, offset: int) -> list[BriefingHistoryItem]:
        briefings = await self._repo.list_briefings(briefing_type, limit, offset)
        return [BriefingHistoryItem(date=b.date, type=b.type, text=b.text) for b in briefings]
