from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.stays.tables import Stay


class StayRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_stay(self, stay_id: int) -> Stay | None:
        return await self._session.get(Stay, stay_id)

    async def get_stays(self, trip_id: int) -> list[Stay]:
        stmt = select(Stay).where(Stay.trip_id == trip_id).order_by(Stay.check_in_at, Stay.id)
        return list((await self._session.scalars(stmt)).all())

    async def create_stay(self, data: dict[str, Any]) -> Stay:
        stay = Stay(**data)
        self._session.add(stay)
        await self._session.commit()
        await self._session.refresh(stay)
        return stay

    async def update_stay(self, stay: Stay, data: dict[str, Any]) -> Stay:
        for field, value in data.items():
            setattr(stay, field, value)
        await self._session.commit()
        await self._session.refresh(stay)
        return stay

    async def delete_stay(self, stay: Stay) -> None:
        await self._session.delete(stay)
        await self._session.commit()
