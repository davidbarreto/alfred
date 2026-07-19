from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.tables import Briefing


class BriefingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_briefing_by_date(self, briefing_date: date, briefing_type: str) -> Briefing | None:
        result = await self._session.execute(
            select(Briefing).where(Briefing.date == briefing_date, Briefing.type == briefing_type)
        )
        return result.scalars().first()

    async def list_briefings(self, briefing_type: str | None, limit: int, offset: int) -> list[Briefing]:
        stmt = select(Briefing).order_by(Briefing.date.desc(), Briefing.type.asc())
        if briefing_type is not None:
            stmt = stmt.where(Briefing.type == briefing_type)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_briefing(self, briefing_date: date, briefing_type: str, text: str) -> Briefing:
        briefing = await self.get_briefing_by_date(briefing_date, briefing_type)
        if briefing is None:
            briefing = Briefing(date=briefing_date, type=briefing_type, text=text)
            self._session.add(briefing)
        else:
            briefing.text = text
        await self._session.flush()
        return briefing
