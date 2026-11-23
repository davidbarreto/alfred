from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.locations.errors import LocationConflictError, LocationValidationError
from app.features.organizer.locations.hours import HoursError, format_hours, format_ranges, hours_on, normalize_hours, open_at
from app.features.organizer.locations.repository import LocationRepository
from app.features.organizer.locations.schemas import (
    LocationCategory,
    LocationCreate,
    LocationFilters,
    LocationRead,
    LocationToday,
    LocationUpdate,
)
from app.features.organizer.locations.tables import HOME_KIND, Location
from app.features.organizer.shopping_categories.tables import ShoppingCategory
from app.shared.protocols.holiday import HolidayProvider
from app.shared.utils.timezone import local_now, local_today

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("name", "kind", "active")

# Called with the old home address and today before it changes, so trips that have already started keep the home
# they were planned with (travel's TripRepository.snapshot_home_value, wired in dependencies.py). Returns the count.
HomeAddressSnapshot = Callable[[str, date], Awaitable[int]]


def _home_address(kind: str, address: str | None) -> str | None:
    """The home address a location stands for: its address when it is the home, else none."""
    return address if kind == HOME_KIND else None


def _hours(value: str | dict | None) -> dict | None:
    try:
        return normalize_hours(value)
    except HoursError as exc:
        raise LocationValidationError(f"Opening hours: {exc}") from exc


def _today(location: Location, now: datetime, holiday: str | None) -> LocationToday:
    day = hours_on(location.opening_hours, now.date(), holiday is not None)
    note = None
    if day.holiday:
        note = "holiday hours" if day.holiday_hours_known else "holiday, hours unknown"
    return LocationToday(
        date=now.date(),
        hours=format_ranges(day.ranges),
        holiday=holiday,
        note=note,
        # Weekday hours on a holiday are only a guess, so "open now" is unknown.
        open_now=open_at(day.ranges, now.time()) if day.holiday_hours_known else None,
    )


def _read(location: Location, now: datetime, holiday: str | None) -> LocationRead:
    return LocationRead(
        id=location.id,
        name=location.name,
        kind=location.kind,
        address=location.address,
        maps_url=location.maps_url,
        opening_hours=location.opening_hours,
        opening_hours_text=format_hours(location.opening_hours),
        notes=location.notes,
        active=location.active,
        categories=[LocationCategory.model_validate(c) for c in location.categories],
        today=_today(location, now, holiday),
        created_at=location.created_at,
        updated_at=location.updated_at,
    )


class LocationService:
    def __init__(
        self,
        session: AsyncSession,
        holiday_provider: HolidayProvider | None = None,
        home_snapshot: HomeAddressSnapshot | None = None,
    ) -> None:
        self._repo = LocationRepository(session)
        # Only the planning holiday calendar (the first of HOLIDAY_CALENDARS) decides holiday hours.
        self._holidays = holiday_provider
        self._home_snapshot = home_snapshot

    async def _keep_old_home(self, old: str | None, new: str | None) -> bool:
        """Before the home address changes, started trips with no home of their own keep the old one.

        Returns whether the snapshot ran: it commits, which expires the ORM objects loaded before it.
        """
        if self._home_snapshot is None or old is None or old == new:
            return False
        count = await self._home_snapshot(old, local_today())
        # Never the address itself: it is personal.
        logger.info("Home address changed: trips_keeping_old_address=%d", count)
        return True

    async def _holiday_today(self, today: date) -> str | None:
        if self._holidays is None:
            return None
        try:
            # No session: a read must not leave an uncommitted provider log row behind.
            found = await self._holidays.get_holidays(today, today)
        except Exception:
            logger.warning("Failed to fetch today's holidays for locations", exc_info=True)
            return None
        names = list(dict.fromkeys(h.name for h in found if h.date == today))
        return ", ".join(names) or None

    async def _to_reads(self, locations: list[Location]) -> list[LocationRead]:
        now = local_now()
        # Only worth a holiday lookup when some location has hours to choose between.
        holiday = await self._holiday_today(now.date()) if any(loc.opening_hours for loc in locations) else None
        return [_read(location, now, holiday) for location in locations]

    async def _to_read(self, location: Location) -> LocationRead:
        return (await self._to_reads([location]))[0]

    async def get(self, location_id: int) -> LocationRead | None:
        location = await self._repo.get(location_id)
        return None if location is None else await self._to_read(location)

    async def find(self, ref: str) -> LocationRead | None:
        """A location by id (digits) or by name (case-insensitive)."""
        ref = ref.strip()
        location = await self._repo.get(int(ref)) if ref.isdigit() else await self._repo.get_by_name(ref)
        return None if location is None else await self._to_read(location)

    async def list(self, filters: LocationFilters) -> list[LocationRead]:
        return await self._to_reads(await self._repo.list(filters))

    async def category_ids_for(self, names: list[str]) -> list[int]:
        """Shopping category ids for names typed in a command; an unknown name is a 422."""
        wanted = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
        found = {c.name.lower(): c.id for c in await self._repo.get_categories_by_name(wanted)}
        missing = [n for n in wanted if n not in found]
        if missing:
            raise LocationValidationError(f"Unknown shopping categories: {', '.join(missing)}")
        return [found[n] for n in wanted]

    async def _categories(self, category_ids: list[int]) -> list[ShoppingCategory]:
        unique = list(dict.fromkeys(category_ids))
        categories = await self._repo.get_categories(unique)
        missing = sorted(set(unique) - {c.id for c in categories})
        if missing:
            raise LocationValidationError(f"Unknown shopping category ids: {missing}")
        return categories

    async def _check_clashes(self, name: str | None, kind: str | None, location_id: int | None) -> None:
        if name is not None:
            other = await self._repo.get_by_name(name)
            if other is not None and other.id != location_id:
                raise LocationConflictError(f"A location named {other.name!r} already exists (id {other.id})")
        if kind == HOME_KIND:
            home = await self._repo.get_home()
            if home is not None and home.id != location_id:
                raise LocationConflictError(f"Home is already set: {home.name!r} (id {home.id})")

    async def create(self, data: LocationCreate) -> LocationRead:
        await self._check_clashes(data.name, data.kind, None)
        fields = data.model_dump(exclude={"category_ids"})
        fields["opening_hours"] = _hours(data.opening_hours)
        categories = await self._categories(data.category_ids)
        location = await self._repo.create(fields, categories)
        logger.info("Location created: id=%d name=%r kind=%s", location.id, location.name, location.kind)
        return await self._to_read(location)

    async def update(self, location_id: int, data: LocationUpdate) -> LocationRead | None:
        changes = data.model_dump(exclude_unset=True)
        for field in _REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise LocationValidationError(f"{field} cannot be cleared")
        current = await self._repo.get(location_id)
        if current is None:
            logger.debug("Location update: id=%d not found", location_id)
            return None
        old_home = _home_address(current.kind, current.address)
        new_home = _home_address(changes.get("kind", current.kind), changes.get("address", current.address))
        await self._check_clashes(changes.get("name"), changes.get("kind"), location_id)
        category_ids = changes.pop("category_ids", None)
        categories = await self._categories(category_ids) if category_ids is not None else None
        if "opening_hours" in changes:
            changes["opening_hours"] = _hours(changes["opening_hours"])
        await self._keep_old_home(old_home, new_home)
        location = await self._repo.update(location_id, changes, categories)
        assert location is not None
        changed = list(changes) + (["category_ids"] if category_ids is not None else [])
        logger.info("Location updated: id=%d name=%r fields=%s", location_id, location.name, changed)
        return await self._to_read(location)

    async def set_categories(self, location_id: int, category_ids: list[int]) -> list[LocationCategory] | None:
        updated = await self.update(location_id, LocationUpdate(category_ids=category_ids))
        return None if updated is None else updated.categories

    async def get_categories(self, location_id: int) -> list[LocationCategory] | None:
        location = await self._repo.get(location_id)
        if location is None:
            return None
        return [LocationCategory.model_validate(c) for c in location.categories]

    async def delete(self, location_id: int) -> bool:
        location = await self._repo.get(location_id)
        if location is None:
            logger.debug("Location delete: id=%d not found", location_id)
            return False
        name, kind = location.name, location.kind
        if await self._keep_old_home(_home_address(kind, location.address), None):
            location = await self._repo.get(location_id) or location
        await self._repo.delete(location)
        logger.info("Location deleted: id=%d name=%r kind=%s", location_id, name, kind)
        return True
