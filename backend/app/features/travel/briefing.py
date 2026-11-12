"""Trip blocks for the morning briefing and the evening digest. `build_*` are pure; `TripBriefService` loads the data."""
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.schemas import TripBrief, TripMarkBrief
from app.features.travel.transaction_links.service import TransactionLinkService
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.schemas import TripDetail
from app.features.travel.trips.service import TripService
from app.features.travel.trips.today import TripToday, build_today
from app.shared.timezone import local_timezone_name, local_today

logger = logging.getLogger(__name__)


def build_agenda(trip: TripDetail, today: date) -> list[str]:
    rows: list[tuple[str, str]] = []
    for item in trip.timeline:
        if item.local.date() == today and item.kind in ("leg", "check_in", "check_out"):
            rows.append((f"{item.local:%H:%M}", item.title))
    for visit in trip.visits:
        if visit.visit_date == today and visit.status != "missed":
            rows.append((f"{visit.visit_time:%H:%M}" if visit.visit_time else "", f"Visit: {visit.place.name}"))
    return [f"{when} {text}".strip() for when, text in sorted(rows, key=lambda r: (r[0] == "", r[0]))]


def build_trip_brief(trip: TripDetail, view: TripToday, spend: Decimal | None) -> TripBrief:
    leave = trip.leave_home_at if trip.leave_home_at and trip.leave_home_at.astimezone(timezone.utc).date() == view.date else None
    return TripBrief(
        trip_name=trip.name, day=(view.date - trip.start_date).days + 1, days=(trip.end_date - trip.start_date).days + 1,
        agenda=build_agenda(trip, view.date), leave_home_at=leave, spend_eur=spend,
    )


class TripBriefService:
    def __init__(self, session: AsyncSession):
        self._trips = TripService(session)
        self._repo = TripRepository(session)
        self._links = TransactionLinkService(session)

    async def _ongoing(self) -> tuple[TripDetail, TripToday] | None:
        today = local_today()
        for trip in await self._repo.get_trips_overlapping(today, today):
            detail = await self._trips.get_trip_detail(trip.id, include_all_visits=True)
            if detail is not None:
                return detail, build_today(detail, datetime.now(timezone.utc), local_timezone_name())
        return None

    async def morning(self) -> TripBrief | None:
        found = await self._ongoing()
        if found is None:
            return None
        detail, view = found
        costs = await self._links.get_trip_costs(detail.id)
        return build_trip_brief(detail, view, costs.total.total_eur if costs else None)

    async def evening(self) -> TripMarkBrief | None:
        found = await self._ongoing()
        if found is None or not found[1].to_mark:
            return None
        return TripMarkBrief(trip_name=found[0].name, to_mark=found[1].to_mark)
