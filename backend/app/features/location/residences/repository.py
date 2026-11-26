from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.residences.tables import Residence


class ResidenceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, residence_id: int) -> Residence | None:
        return await self._session.get(Residence, residence_id)

    async def get_all(self) -> list[Residence]:
        """Every row, newest first (the birth row, with no start, last). There are few: a lifetime's homes."""
        stmt = select(Residence).order_by(Residence.from_date.desc().nulls_last(), Residence.id.desc())
        return list((await self._session.scalars(stmt)).all())

    async def get_page(self, limit: int, offset: int) -> list[Residence]:
        stmt = (
            select(Residence).order_by(Residence.from_date.desc().nulls_last(), Residence.id.desc())
            .limit(limit).offset(offset)
        )
        return list((await self._session.scalars(stmt)).all())

    async def count_in_city(self, city_id: int) -> int:
        stmt = select(func.count()).select_from(Residence).where(Residence.city_id == city_id)
        return int(await self._session.scalar(stmt) or 0)

    async def add(self, residence: Residence) -> None:
        self._session.add(residence)
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def refresh(self, residence: Residence) -> None:
        await self._session.refresh(residence)

    async def delete(self, residence: Residence) -> None:
        await self._session.delete(residence)
        await self._session.commit()
