import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.organizer.calendar_events.service import CalendarEventService
from app.features.travel.checklist.service import ChecklistService
from app.features.travel.legs.repository import LegRepository
from app.features.travel.legs.schemas import LegRead
from app.features.travel.notes_index import LEG_NOTE, TRIP_NOTE, TravelNoteIndex
from app.features.travel.settings_service import TravelSettingsService
from app.features.travel.stays.repository import StayRepository
from app.features.travel.stays.schemas import StayRead
from app.features.travel.tags.repository import TravelTagRepository
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import (
    TripCreate, TripDetail, TripFilters, TripListItem, TripLocations, TripRead, TripUpdate,
)
from app.features.travel.visits.repository import VisitRepository
from app.features.travel.visits.schemas import VisitRead
from app.features.travel.trips.map_points import MapScope, TripMap, build_trip_map
from app.features.travel.trips.ideas import build_ideas
from app.features.travel.trips.today import TripToday, build_today
from app.features.travel.trips.coverage_warnings import (
    find_booking_reference_warnings, find_chain_warnings, find_event_warnings, find_lodging_warnings,
    find_outside_dates_warnings, find_stay_overlap_warnings, find_unpaid_leg_warnings, find_unpaid_stay_warnings,
    find_visit_overlap_warnings, find_visit_warnings,
)
from app.features.travel.trips.timeline import TripWarning, build_timeline, find_warnings, leave_home_at
from app.shared.timezone import local_timezone, local_timezone_name, local_today

logger = logging.getLogger(__name__)

# The checklist nudge starts this many days before the trip.
CHECKLIST_NUDGE_DAYS = 60
_NOT_NULL = ("name", "start_date", "end_date")


class TripService:
    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None):
        self._notes = TravelNoteIndex(embedding_service)
        self._repo = TripRepository(session)
        self._tag_repo = TravelTagRepository(session)
        self._leg_repo = LegRepository(session)
        self._stay_repo = StayRepository(session)
        self._visit_repo = VisitRepository(session)
        self._link_repo = TransactionLinkRepository(session)
        self._checklist = ChecklistService(session)
        self.settings_service = TravelSettingsService(session)
        # The local calendar copy only: warnings never call Google.
        self._calendar = CalendarEventService(provider=None, session=session)

    async def get_trips(self, filters: TripFilters) -> list[TripListItem]:
        trips = await self._repo.get_trips(filters, local_today())
        logger.debug("Trips listed: count=%d status=%s", len(trips), filters.status)
        locations = await self._repo.get_trip_locations([t.id for t in trips]) if trips else {}
        items = []
        for trip in trips:
            cities, countries = locations.get(trip.id, ([], []))
            items.append(TripListItem.model_validate(trip).model_copy(update={"cities": cities, "countries": countries}))
        return items

    async def get_locations(self) -> TripLocations:
        cities, countries = await self._repo.get_locations()
        return TripLocations(cities=cities, countries=countries)

    async def get_trip(self, trip_id: int) -> TripRead | None:
        trip = await self._repo.get_trip(trip_id)
        return TripRead.model_validate(trip) if trip else None

    async def get_trip_detail(self, trip_id: int, include_all_visits: bool = False) -> TripDetail | None:
        trip = await self._repo.get_trip(trip_id)
        if trip is None:
            return None
        legs = [LegRead.model_validate(leg) for leg in await self._leg_repo.get_legs(trip_id)]
        stays = [StayRead.model_validate(s) for s in await self._stay_repo.get_stays(trip_id)]
        visits = [VisitRead.model_validate(v) for v in await self._visit_repo.get_trip_visits(trip_id)]
        all_visits = visits
        # Once the trip is over, what stayed planned or missed is noise unless the user asks to see it.
        hidden = 0
        if trip.end_date < local_today() and not include_all_visits:
            shown = [v for v in visits if v.status == "visited"]
            hidden, visits = len(visits) - len(shown), shown
        settings = await self.settings_service.get()
        leave_at = leave_home_at(legs, settings.airport_buffer_min + settings.home_to_airport_min)
        today = local_today()
        paid_legs = await self._link_repo.get_linked_ids("legs", [leg.id for leg in legs])
        paid_stays = await self._link_repo.get_linked_ids("stays", [stay.id for stay in stays])
        warnings = [
            *find_warnings(legs, stays),
            *find_lodging_warnings(legs, stays),
            *find_visit_warnings(all_visits, legs, stays, settings.max_visits_per_day),
            *find_outside_dates_warnings(legs, stays, all_visits, trip.start_date, trip.end_date),
            *find_chain_warnings(legs),
            *find_stay_overlap_warnings(stays),
            *find_unpaid_leg_warnings(legs, paid_legs, trip.start_date, today, settings.unpaid_leg_days),
            *find_unpaid_stay_warnings(stays, paid_stays, trip.start_date, today, settings.unpaid_leg_days),
            *find_booking_reference_warnings(legs, stays, trip.start_date, today, settings.unpaid_leg_days),
            *find_visit_overlap_warnings(all_visits, settings.visit_duration_min),
            *find_event_warnings(all_visits, await self._linked_events(all_visits), today, local_timezone()),
        ]
        if 0 <= (trip.start_date - today).days <= CHECKLIST_NUDGE_DAYS and await self._checklist.is_pending(trip.name):
            warnings.append(TripWarning(
                kind="checklist_not_generated",
                message="The pre-trip checklist has not been generated yet (the Generate checklist button below)",
            ))
        ideas = []
        if trip.end_date >= local_today():
            wishlist = await self._visit_repo.get_wishlist_in_cities([s.place.city for s in stays if s.place.city])
            ideas = build_ideas(all_visits, [VisitRead.model_validate(v) for v in wishlist], stays)
        return TripDetail(
            **TripRead.model_validate(trip).model_dump(exclude={"status"}),
            legs=legs,
            stays=stays,
            timeline=build_timeline(legs, stays, leave_at, settings.home_address, warnings),
            warnings=warnings,
            leave_home_at=leave_at,
            visits=visits,
            hidden_visit_count=hidden,
            ideas=ideas,
        )

    async def _linked_events(self, visits: list[VisitRead]) -> dict:
        events = {}
        for visit in visits:
            if visit.calendar_event_id is not None:
                event = await self._calendar.get_event(visit.calendar_event_id)
                if event is not None:
                    events[visit.calendar_event_id] = event
        return events

    async def get_today(self, trip_id: int) -> TripToday | None:
        """The next step and today's visits; planned and missed visits of past days stay out (include_all_visits)."""
        detail = await self.get_trip_detail(trip_id, include_all_visits=True)
        if detail is None:
            return None
        return build_today(detail, datetime.now(timezone.utc), local_timezone_name())

    async def get_trip_map(self, trip_id: int, scope: MapScope = "all") -> TripMap | None:
        trip = await self._repo.get_trip(trip_id)
        if trip is None:
            return None
        legs = [LegRead.model_validate(leg) for leg in await self._leg_repo.get_legs(trip_id)]
        stays = [StayRead.model_validate(s) for s in await self._stay_repo.get_stays(trip_id)]
        visits = [VisitRead.model_validate(v) for v in await self._visit_repo.get_trip_visits(trip_id)]
        result = build_trip_map(trip.id, trip.name, legs, stays, visits, datetime.now(timezone.utc), scope)
        logger.debug("Trip map: id=%d scope=%s points=%d", trip_id, scope, len(result.points))
        return result

    async def create_trip(self, data: TripCreate) -> TripRead:
        fields = data.model_dump(exclude={"tags"})
        tags = await self._tag_repo.get_or_create_tags(data.tags)
        trip = await self._repo.create_trip(fields, tags)
        logger.info("Trip created: id=%d name=%r", trip.id, trip.name)
        await self._notes.sync(TRIP_NOTE, trip.id, f"Trip {trip.name}", trip.notes)
        return TripRead.model_validate(trip)

    async def update_trip(self, trip_id: int, data: TripUpdate) -> TripRead | None:
        trip = await self._repo.get_trip(trip_id)
        if trip is None:
            logger.debug("Trip update: id=%d not found", trip_id)
            return None
        changes = data.model_dump(exclude_unset=True, exclude={"tags"})
        for field in _NOT_NULL:
            if field in changes and changes[field] is None:
                raise ValueError(f"{field} cannot be null")
        if changes.get("end_date", trip.end_date) < changes.get("start_date", trip.start_date):
            raise ValueError("end_date cannot be before start_date")
        tags = None
        if data.tags is not None:
            tags = await self._tag_repo.get_or_create_tags(data.tags)
        trip = await self._repo.update_trip(trip, changes, tags)
        fields = list(changes.keys()) + (["tags"] if tags is not None else [])
        logger.info("Trip updated: id=%d fields=%s", trip_id, fields)
        if "notes" in changes or "name" in changes:
            await self._notes.sync(TRIP_NOTE, trip.id, f"Trip {trip.name}", trip.notes)
        return TripRead.model_validate(trip)

    async def delete_trip(self, trip_id: int) -> bool:
        # Legs go with the trip, so their note embeddings must too; stays and visits keep theirs.
        leg_ids = [leg.id for leg in await self._leg_repo.get_legs(trip_id)]
        deleted = await self._repo.delete_trip(trip_id)
        if deleted:
            logger.info("Trip deleted: id=%d", trip_id)
            await self._notes.remove(TRIP_NOTE, trip_id)
            for leg_id in leg_ids:
                await self._notes.remove(LEG_NOTE, leg_id)
        return deleted
