import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.default_tags import parse_default_tag_names
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.legs.repository import LegRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.transaction_links.schemas import (
    Cost,
    EntityCost,
    KindCost,
    LinkedTransaction,
    LinkedTransactions,
    LinkKind,
    PlaceCosts,
    TripCosts,
)
from app.features.travel.trips.repository import TripRepository
from app.features.travel.places.repository import PlaceRepository
from app.features.travel.visits.repository import VisitRepository

logger = logging.getLogger(__name__)

# Tagged charges count as trip charges from this long before the trip until this long after it (prepaid bookings).
TAG_LEAD_DAYS = 90
TAG_TAIL_DAYS = 30

_NO_COST = (Decimal("0.00"), 0, 0)


class TransferNotLinkableError(ValueError):
    """Transfers move money between the user's own accounts; they are not a trip cost."""


def _cost(row: tuple[Decimal, int, int]) -> Cost:
    total, count, unconverted = row
    return Cost(total_eur=total, transaction_count=count, unconverted_count=unconverted)


class TransactionLinkService:
    def __init__(self, session: AsyncSession):
        self._repo = TransactionLinkRepository(session)
        self._trip_repo = TripRepository(session)
        self._place_repo = PlaceRepository(session)
        self._leg_repo = LegRepository(session)
        self._stay_repo = StayRepository(session)
        self._visit_repo = VisitRepository(session)

    async def _require(self, kind: LinkKind, entity_id: int) -> None:
        if not await self._repo.entity_exists(kind, entity_id):
            raise TravelNotFoundError(f"{kind[:-1].capitalize()} {entity_id} not found")

    async def get_linked(self, kind: LinkKind, entity_id: int) -> LinkedTransactions:
        await self._require(kind, entity_id)
        transactions = await self._repo.get_linked(kind, entity_id)
        costs = await self._repo.get_entity_costs(kind, [entity_id])
        logger.debug("Linked transactions listed: kind=%s id=%d count=%d", kind, entity_id, len(transactions))
        return LinkedTransactions(
            transactions=[LinkedTransaction.model_validate(t) for t in transactions],
            cost=_cost(costs.get(entity_id, _NO_COST)),
        )

    async def link(self, kind: LinkKind, entity_id: int, transaction_id: int) -> LinkedTransactions:
        """Idempotent: linking the same transaction twice leaves one link."""
        await self._require(kind, entity_id)
        transaction = await self._repo.get_transaction(transaction_id)
        if transaction is None:
            raise TravelNotFoundError(f"Transaction {transaction_id} not found")
        if transaction.type == "transfer":
            raise TransferNotLinkableError("Transfers can't be linked to a trip")
        await self._repo.link(kind, entity_id, transaction_id)
        logger.info("Transaction linked: kind=%s id=%d transaction_id=%d", kind, entity_id, transaction_id)
        return await self.get_linked(kind, entity_id)

    async def unlink(self, kind: LinkKind, entity_id: int, transaction_id: int) -> bool:
        await self._require(kind, entity_id)
        removed = await self._repo.unlink(kind, entity_id, transaction_id)
        if removed:
            logger.info("Transaction unlinked: kind=%s id=%d transaction_id=%d", kind, entity_id, transaction_id)
        return removed

    async def get_trip_costs(self, trip_id: int) -> TripCosts | None:
        if await self._trip_repo.get_trip(trip_id) is None:
            return None
        legs = await self._leg_repo.get_legs(trip_id)
        stays = await self._stay_repo.get_stays(trip_id)
        visits = await self._visit_repo.get_trip_visits(trip_id)

        async def per_entity(kind: LinkKind, items: list) -> list[EntityCost]:
            costs = await self._repo.get_entity_costs(kind, [i.id for i in items])
            return [EntityCost(id=i.id, **_cost(costs[i.id]).model_dump()) for i in items if i.id in costs]

        by_kind = await self._repo.get_trip_costs_by_kind(trip_id)
        return TripCosts(
            total=_cost(await self._repo.get_trip_total(trip_id)),
            by_kind=[KindCost(kind=kind, **_cost(row).model_dump()) for kind, row in by_kind.items()],
            legs=await per_entity("legs", legs),
            stays=await per_entity("stays", stays),
            visits=await per_entity("visits", visits),
        )

    async def get_unlinked(self, trip_id: int) -> list[LinkedTransaction] | None:
        """Charges that look like part of the trip but are not linked to any leg, stay or visit yet."""
        trip = await self._trip_repo.get_trip(trip_id)
        if trip is None:
            return None
        found = await self._repo.get_unlinked(
            datetime.combine(trip.start_date, time.min),
            datetime.combine(trip.end_date + timedelta(days=1), time.min),
            parse_default_tag_names(trip.default_tag_names),
            datetime.combine(trip.start_date - timedelta(days=TAG_LEAD_DAYS), time.min),
            datetime.combine(trip.end_date + timedelta(days=TAG_TAIL_DAYS + 1), time.min),
        )
        logger.debug("Unlinked transactions: trip_id=%d count=%d", trip_id, len(found))
        return [LinkedTransaction.model_validate(t) for t in found]

    async def get_place_costs(self, place_id: int) -> PlaceCosts | None:
        if await self._place_repo.get_place(place_id) is None:
            return None
        return PlaceCosts(total=_cost(await self._repo.get_place_total(place_id)))
