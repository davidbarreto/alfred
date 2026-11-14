"""Finance tags a trip stamps on the expenses dated within it (`trips.default_tag_names`)."""
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.tags.repository import TagRepository
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.trips.repository import TripRepository
from app.shared.tags import normalize_tag_name

logger = logging.getLogger(__name__)

# Only spending is stamped: a refund or a transfer inside a trip is not a trip expense by itself.
TAGGED_TYPE = "expense"


def parse_default_tag_names(text: str | None) -> list[str]:
    """Split on commas into normalized (trimmed, lowercase) tag names, dropping empties and duplicates."""
    names: list[str] = []
    seen: set[str] = set()
    for part in (text or "").split(","):
        name = normalize_tag_name(part)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


@dataclass(frozen=True)
class TripTagWindow:
    start: date
    end: date
    names: list[str]


class TripTagWindows:
    """The default tags of every trip around a date range, loaded once and queried per transaction."""

    def __init__(self, windows: list[TripTagWindow]):
        self._windows = windows

    def names_for(self, day: date, transaction_type: str) -> list[str]:
        if transaction_type != TAGGED_TYPE:
            return []
        names: list[str] = []
        seen: set[str] = set()
        for window in self._windows:
            if window.start <= day <= window.end:
                for name in window.names:
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        names.append(name)
        return names


class TripDefaultTagService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._trip_repo = TripRepository(session)
        self._tag_repo = TagRepository(session)
        self._link_repo = TransactionLinkRepository(session)

    async def windows_for(self, first: date, last: date) -> TripTagWindows:
        trips = await self._trip_repo.get_trips_in_window(first, last)
        return TripTagWindows([
            TripTagWindow(t.start_date, t.end_date, names)
            for t in trips
            if (names := parse_default_tag_names(t.default_tag_names))
        ])

    async def names_for(self, day: date, transaction_type: str) -> list[str]:
        return (await self.windows_for(day, day)).names_for(day, transaction_type)

    async def apply_to_existing(self, trip_id: int) -> tuple[list[str], int]:
        """Tag the trip's existing expenses; returns the tag names and how many transaction-tag rows were added."""
        trip = await self._trip_repo.get_trip(trip_id)
        if trip is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        names = parse_default_tag_names(trip.default_tag_names)
        if not names:
            return [], 0
        tags = await self._tag_repo.resolve_tags(names)
        await self._session.flush()
        start = datetime.combine(trip.start_date, time.min)
        end = datetime.combine(trip.end_date + timedelta(days=1), time.min)
        added = await self._link_repo.tag_expenses_between(start, end, [t.id for t in tags])
        logger.info("Trip default tags applied: trip_id=%d tags=%d added=%d", trip_id, len(names), added)
        return names, added
