import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.repository import LegRepository
from app.features.travel.legs.schemas import LegCreate, LegRead, LegUpdate
from app.features.travel.trips.repository import TripRepository
from app.features.travel.zones import to_utc

logger = logging.getLogger(__name__)

_NOT_NULL = ("mode", "origin", "destination", "departs_at", "arrives_at", "departs_tz", "arrives_tz")


class LegService:
    def __init__(self, session: AsyncSession):
        self._repo = LegRepository(session)
        self._trip_repo = TripRepository(session)

    async def get_legs(self, trip_id: int) -> list[LegRead]:
        legs = await self._repo.get_legs(trip_id)
        logger.debug("Legs listed: trip_id=%d count=%d", trip_id, len(legs))
        return [LegRead.model_validate(leg) for leg in legs]

    async def get_leg(self, leg_id: int) -> LegRead | None:
        leg = await self._repo.get_leg(leg_id)
        return LegRead.model_validate(leg) if leg else None

    async def create_leg(self, data: LegCreate) -> LegRead:
        if await self._trip_repo.get_trip(data.trip_id) is None:
            raise TravelNotFoundError(f"Trip {data.trip_id} not found")
        leg = await self._repo.create_leg(data.model_dump())
        logger.info("Leg created: id=%d trip_id=%d mode=%s", leg.id, leg.trip_id, leg.mode)
        return LegRead.model_validate(leg)

    async def update_leg(self, leg_id: int, data: LegUpdate) -> LegRead | None:
        leg = await self._repo.get_leg(leg_id)
        if leg is None:
            logger.debug("Leg update: id=%d not found", leg_id)
            return None
        changes = data.model_dump(exclude_unset=True)
        for field in _NOT_NULL:
            if field in changes and changes[field] is None:
                raise ValueError(f"{field} cannot be null")
        departs_tz = changes.get("departs_tz", leg.departs_tz)
        arrives_tz = changes.get("arrives_tz", leg.arrives_tz)
        if "departs_at" in changes:
            changes["departs_at"] = to_utc(changes["departs_at"], departs_tz)
        if "arrives_at" in changes:
            changes["arrives_at"] = to_utc(changes["arrives_at"], arrives_tz)
        if changes.get("arrives_at", leg.arrives_at) < changes.get("departs_at", leg.departs_at):
            raise ValueError("arrives_at cannot be before departs_at")
        leg = await self._repo.update_leg(leg, changes)
        logger.info("Leg updated: id=%d fields=%s", leg_id, list(changes.keys()))
        return LegRead.model_validate(leg)

    async def delete_leg(self, leg_id: int) -> bool:
        leg = await self._repo.get_leg(leg_id)
        if leg is None:
            return False
        await self._repo.delete_leg(leg)
        logger.info("Leg deleted: id=%d trip_id=%d", leg_id, leg.trip_id)
        return True
