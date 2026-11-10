from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.legs.tables import Leg


class LegRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_leg(self, leg_id: int) -> Leg | None:
        return await self._session.get(Leg, leg_id)

    async def get_leg_by_calendar_event(self, event_id: int) -> Leg | None:
        return await self._session.scalar(select(Leg).where(Leg.calendar_event_id == event_id))

    async def get_imported_event_ids(self, event_ids: list[int]) -> dict[int, int]:
        """Calendar event id -> id of the leg imported from it, for the given events."""
        if not event_ids:
            return {}
        stmt = select(Leg.calendar_event_id, Leg.id).where(Leg.calendar_event_id.in_(event_ids))
        return {event_id: leg_id for event_id, leg_id in (await self._session.execute(stmt)).all()}

    async def get_legs(self, trip_id: int) -> list[Leg]:
        stmt = select(Leg).where(Leg.trip_id == trip_id).order_by(Leg.departs_at, Leg.id)
        return list((await self._session.scalars(stmt)).all())

    async def create_leg(self, data: dict[str, Any]) -> Leg:
        leg = Leg(**data)
        self._session.add(leg)
        await self._session.commit()
        await self._session.refresh(leg)
        return leg

    async def update_leg(self, leg: Leg, data: dict[str, Any]) -> Leg:
        for field, value in data.items():
            setattr(leg, field, value)
        await self._session.commit()
        await self._session.refresh(leg)
        return leg

    async def delete_leg(self, leg: Leg) -> None:
        await self._session.delete(leg)
        await self._session.commit()
