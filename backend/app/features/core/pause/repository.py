from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.pause.tables import PauseLog


class PauseLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        started_at: datetime,
        ended_at: datetime,
        tasks_urgency_reset: int,
        tasks_deadline_shifted: int,
    ) -> PauseLog:
        log = PauseLog(
            started_at=started_at,
            ended_at=ended_at,
            tasks_urgency_reset=tasks_urgency_reset,
            tasks_deadline_shifted=tasks_deadline_shifted,
        )
        self._session.add(log)
        await self._session.commit()
        await self._session.refresh(log)
        return log

    async def list(self, limit: int = 100) -> list[PauseLog]:
        result = await self._session.execute(
            select(PauseLog).order_by(PauseLog.started_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
