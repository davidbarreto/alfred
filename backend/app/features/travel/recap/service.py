import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.recap.builder import build_recap
from app.features.travel.recap.schemas import TripRecap
from app.features.travel.transaction_links.service import TransactionLinkService
from app.features.travel.trips.service import TripService

logger = logging.getLogger(__name__)


class TripRecapService:
    def __init__(self, session: AsyncSession):
        self._trips = TripService(session)
        self._links = TransactionLinkService(session)

    async def get_recap(self, trip_id: int) -> TripRecap | None:
        # All visits, hidden ones included: the recap counts what was missed or never done.
        detail = await self._trips.get_trip_detail(trip_id, include_all_visits=True)
        if detail is None:
            return None
        recap = build_recap(detail, await self._links.get_trip_costs(trip_id))
        logger.debug("Trip recap built: id=%d to_complete=%d", trip_id, len(recap.to_complete))
        return recap
