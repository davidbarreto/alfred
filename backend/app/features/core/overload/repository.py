from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.overload.tables import OverloadLog


class OverloadLogRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_day(self, day: date) -> OverloadLog | None:
        result = await self._session.execute(select(OverloadLog).where(OverloadLog.date == day))
        return result.scalars().first()

    async def get_latest(self) -> OverloadLog | None:
        result = await self._session.execute(select(OverloadLog).order_by(OverloadLog.date.desc()).limit(1))
        return result.scalars().first()

    async def get_days(self, since: date) -> list[OverloadLog]:
        result = await self._session.execute(
            select(OverloadLog).where(OverloadLog.date >= since).order_by(OverloadLog.date.desc())
        )
        return list(result.scalars().all())

    async def save(self, row: OverloadLog) -> OverloadLog:
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return row
