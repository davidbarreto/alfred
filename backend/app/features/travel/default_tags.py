"""Finance tags stamped on expenses: a trip's (`trips.default_tag_names`) on the days within it, and a city's (its
name, lowercase, plus its `default_tag_names`) on the days of a stay there, check-in to check-out day.

A city is never stamped on a day the user lived there (`location.residences`), nor when it is the Home place's city.
"""
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.tags.repository import TagRepository
from app.features.location.cities.tables import City
from app.features.location.places.repository import PlaceRepository
from app.features.location.residences.periods import Period, lived_on
from app.features.location.residences.repository import ResidenceRepository
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.stays.repository import StayRepository
from app.features.travel.stays.tables import Stay
from app.features.travel.transaction_links.repository import TransactionLinkRepository
from app.features.travel.trips.repository import TripRepository
from app.features.travel.zones import to_local
from app.shared.utils.tags import normalize_tag_name

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


def city_tag_names(city: City) -> list[str]:
    """What a stay in the city stamps: its name (trimmed, lowercase), then its default tags."""
    name = normalize_tag_name(city.name)
    return ([name] if name else []) + [n for n in parse_default_tag_names(city.default_tag_names) if n != name]


def city_tag_groups(city: City) -> list[list[str]]:
    """The tag sets that count a charge for the city's spend: its name alone, or all of its default tags."""
    name = normalize_tag_name(city.name)
    groups = [[name]] if name else []
    defaults = parse_default_tag_names(city.default_tag_names)
    return groups + ([defaults] if defaults and defaults not in groups else [])


@dataclass(frozen=True)
class TripTagWindow:
    start: date
    end: date
    names: list[str]
    # Days inside [start, end] that get nothing (a city's days lived there).
    skip: frozenset[date] = field(default_factory=frozenset)

    def days(self) -> list[date]:
        return [d for d in (self.start + timedelta(days=i) for i in range((self.end - self.start).days + 1)) if d not in self.skip]


def stay_window(stay: Stay, lived: list[Period], home_city_id: int | None) -> TripTagWindow | None:
    """The stay's city tags over its local check-in to check-out dates, without the days lived there; none for the
    home city or a city with no tags."""
    city = stay.place.city
    names = city_tag_names(city)
    if not names or city.id == home_city_id:
        return None
    start, end = to_local(stay.check_in_at, stay.timezone).date(), to_local(stay.check_out_at, stay.timezone).date()
    skip = frozenset(d for d in TripTagWindow(start, end, names).days() if lived_on(d, lived))
    window = TripTagWindow(start, end, names, skip)
    return window if window.days() else None


def _runs(days: list[date]) -> list[tuple[date, date]]:
    """Consecutive days as [first, last] runs."""
    runs: list[tuple[date, date]] = []
    for day in sorted(days):
        if runs and runs[-1][1] + timedelta(days=1) == day:
            runs[-1] = (runs[-1][0], day)
        else:
            runs.append((day, day))
    return runs


class TripTagWindows:
    """The default tags of every trip and the city tags of every stay around a date range, loaded once and queried
    per transaction."""

    def __init__(self, windows: list[TripTagWindow]):
        self._windows = windows

    def names_for(self, day: date, transaction_type: str) -> list[str]:
        if transaction_type != TAGGED_TYPE:
            return []
        names: list[str] = []
        seen: set[str] = set()
        for window in self._windows:
            if window.start <= day <= window.end and day not in window.skip:
                for name in window.names:
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        names.append(name)
        return names


class TripDefaultTagService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._trip_repo = TripRepository(session)
        self._stay_repo = StayRepository(session)
        self._tag_repo = TagRepository(session)
        self._link_repo = TransactionLinkRepository(session)
        self._residence_repo = ResidenceRepository(session)
        self._place_repo = PlaceRepository(session)

    async def _stay_windows(self, stays: list[Stay]) -> list[TripTagWindow]:
        if not stays:
            return []
        lived: dict[int, list[Period]] = {}
        for row in await self._residence_repo.get_all():
            lived.setdefault(row.city_id, []).append(row)
        home = await self._place_repo.get_home()
        home_city_id = home.city_id if home else None
        return [w for s in stays if (w := stay_window(s, lived.get(s.place.city_id, []), home_city_id))]

    async def windows_for(self, first: date, last: date) -> TripTagWindows:
        trips = await self._trip_repo.get_trips_in_window(first, last)
        # Stays are stored in UTC: a day of margin either side catches every local date, the windows do the rest.
        stays = await self._stay_repo.get_stays_between(
            datetime.combine(first - timedelta(days=1), time.min, timezone.utc),
            datetime.combine(last + timedelta(days=2), time.min, timezone.utc),
        )
        return TripTagWindows([
            TripTagWindow(t.start_date, t.end_date, names)
            for t in trips
            if (names := parse_default_tag_names(t.default_tag_names))
        ] + await self._stay_windows(stays))

    async def names_for(self, day: date, transaction_type: str) -> list[str]:
        return (await self.windows_for(day, day)).names_for(day, transaction_type)

    async def _tag_days(self, days: list[date], names: list[str]) -> int:
        tags = await self._tag_repo.resolve_tags(names)
        await self._session.flush()
        added = 0
        for first, last in _runs(days):
            start = datetime.combine(first, time.min)
            added += await self._link_repo.tag_expenses_between(start, datetime.combine(last + timedelta(days=1), time.min), [t.id for t in tags])
        return added

    async def _apply_windows(self, windows: list[TripTagWindow]) -> tuple[list[str], int]:
        names: list[str] = []
        added = 0
        for window in windows:
            added += await self._tag_days(window.days(), window.names)
            names += [n for n in window.names if n not in names]
        return names, added

    async def apply_to_existing(self, trip_id: int) -> tuple[list[str], int]:
        """Tag the trip's existing expenses with its default tags and its stays' city tags; returns the tag names and
        how many transaction-tag rows were added."""
        trip = await self._trip_repo.get_trip(trip_id)
        if trip is None:
            raise TravelNotFoundError(f"Trip {trip_id} not found")
        trip_names = parse_default_tag_names(trip.default_tag_names)
        windows = [TripTagWindow(trip.start_date, trip.end_date, trip_names)] if trip_names else []
        windows += await self._stay_windows(await self._stay_repo.get_stays(trip_id))
        names, added = await self._apply_windows(windows)
        logger.info("Trip default tags applied: trip_id=%d tags=%d added=%d", trip_id, len(names), added)
        return names, added

    async def apply_to_stay(self, stay: Stay) -> int:
        """Tag the expenses already dated on the stay's days with its city's tags (a new or moved stay)."""
        names, added = await self._apply_windows(await self._stay_windows([stay]))
        if names:
            logger.info("Stay city tags applied: stay_id=%d tags=%d added=%d", stay.id, len(names), added)
        return added
