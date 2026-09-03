from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.insights.schemas import InterviewInsightFilters
from app.features.organizer.interviews.insights.tables import InterviewInsight


class InterviewInsightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_insight(
        self, content: str, model: str, process_ids: list[int], generated_at: datetime
    ) -> InterviewInsight:
        insight = InterviewInsight(
            content=content, model=model, process_ids=process_ids, generated_at=generated_at
        )
        self._session.add(insight)
        await self._session.commit()
        await self._session.refresh(insight)
        return insight

    async def get_insights(self, filters: InterviewInsightFilters) -> list[InterviewInsight]:
        stmt = (
            select(InterviewInsight)
            .order_by(InterviewInsight.generated_at.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
