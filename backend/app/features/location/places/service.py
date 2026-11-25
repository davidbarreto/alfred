from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.errors import LocationConflictError, LocationNotFoundError, LocationValidationError
from app.features.location.hooks import PlaceHooks
from app.features.location.places.constants import HOME_KIND
from app.features.location.places.coordinates import coordinates_from_maps_url
from app.features.location.places.hours import HoursError, format_ranges, hours_on, normalize_hours, open_at
from app.features.location.places.repository import PlaceRepository
from app.features.location.places.schemas import PlaceCreate, PlaceFilters, PlaceRead, PlaceToday, PlaceUpdate
from app.features.location.places.tables import Place
from app.shared.protocols.holiday import HolidayProvider
from app.shared.utils.timezone import local_now, local_today

logger = logging.getLogger(__name__)

_REQUIRED_FIELDS = ("name", "kind", "city_id", "active")



@dataclass(frozen=True)
class HomeValues:
    """The home address and home city a place stands for: its own when it is the Home place, else none."""
    address: str | None = None
    city_id: int | None = None


# Called before Home's address or city changes with the old values that change (the others None) and today, so trips
# that have already started keep the home they were planned with (travel's TripRepository.snapshot_home_value, wired
# in dependencies.py). Returns the number of trips that kept an old value.
HomeSnapshot = Callable[[HomeValues, date], Awaitable[int]]


def _home_values(kind: str, address: str | None, city_id: int | None) -> HomeValues:
    return HomeValues(address, city_id) if kind == HOME_KIND else HomeValues()


def _hours(value: str | dict | None) -> dict | None:
    try:
        return normalize_hours(value)
    except HoursError as exc:
        raise LocationValidationError(f"Opening hours: {exc}") from exc


def _today(place: Place, now: datetime, holiday: str | None) -> PlaceToday:
    day = hours_on(place.opening_hours, now.date(), holiday is not None)
    note = None
    if day.holiday:
        note = "holiday hours" if day.holiday_hours_known else "holiday, hours unknown"
    return PlaceToday(
        date=now.date(),
        hours=format_ranges(day.ranges),
        holiday=holiday,
        note=note,
        # Weekday hours on a holiday are only a guess, so "open now" is unknown.
        open_now=open_at(day.ranges, now.time()) if day.holiday_hours_known else None,
    )


def _coordinate_fields(coordinates: tuple[float, float] | None, maps_url: str | None) -> dict:
    """latitude/longitude to store: the typed ones, else the Maps link's, else none."""
    lat_lon = coordinates or coordinates_from_maps_url(maps_url)
    return {"latitude": lat_lon[0], "longitude": lat_lon[1]} if lat_lon else {"latitude": None, "longitude": None}


class PlaceService:
    """What a place is: create, update, archive and delete, opening hours, coordinates and the home rules.

    The domains that use places (organizer's everyday role, travel's trip role) are told through `hooks`.
    """

    def __init__(
        self,
        session: AsyncSession,
        hooks: Sequence[PlaceHooks] = (),
        holiday_provider: HolidayProvider | None = None,
        home_snapshot: HomeSnapshot | None = None,
    ) -> None:
        self._repo = PlaceRepository(session)
        self._hooks = tuple(hooks)
        # Only the planning holiday calendar (the first of HOLIDAY_CALENDARS) decides holiday hours.
        self._holidays = holiday_provider
        self._home_snapshot = home_snapshot

    async def _keep_old_home(self, old: HomeValues, new: HomeValues) -> None:
        """Before the home address or city changes, started trips with no home of their own keep the old one.

        An old value that was never set is not copied.
        """
        changed = HomeValues(
            address=old.address if old.address is not None and old.address != new.address else None,
            city_id=old.city_id if old.city_id is not None and old.city_id != new.city_id else None,
        )
        if self._home_snapshot is None or changed == HomeValues():
            return
        count = await self._home_snapshot(changed, local_today())
        # Never the address itself: it is personal.
        logger.info(
            "Home changed: address=%s city=%s trips_keeping_old_home=%d",
            changed.address is not None, changed.city_id is not None, count,
        )

    async def _holiday_today(self, today: date) -> str | None:
        if self._holidays is None:
            return None
        try:
            # No session: a read must not leave an uncommitted provider log row behind.
            found = await self._holidays.get_holidays(today, today)
        except Exception:
            logger.warning("Failed to fetch today's holidays for places", exc_info=True)
            return None
        names = list(dict.fromkeys(h.name for h in found if h.date == today))
        return ", ".join(names) or None

    async def reads(self, places: Sequence[Place]) -> list[PlaceRead]:
        """Places as returned by the API, each with today's hours."""
        now = local_now()
        # Only worth a holiday lookup when some place has hours to choose between.
        holiday = await self._holiday_today(now.date()) if any(p.opening_hours for p in places) else None
        return [
            PlaceRead.model_validate(place).model_copy(update={"today": _today(place, now, holiday)})
            for place in places
        ]

    async def _read(self, place: Place) -> PlaceRead:
        return (await self.reads([place]))[0]

    async def get_row(self, place_id: int) -> Place | None:
        """The place as stored, for the domains that build their own view of it."""
        return await self._repo.get(place_id)

    async def names(self) -> dict[int, str]:
        """Every place's name by id, archived ones too."""
        return await self._repo.names()

    async def get(self, place_id: int) -> PlaceRead | None:
        place = await self._repo.get(place_id)
        return None if place is None else await self._read(place)

    async def get_home(self) -> PlaceRead | None:
        home = await self._repo.get_home()
        return None if home is None else await self._read(home)

    async def list(self, filters: PlaceFilters) -> list[PlaceRead]:
        places = await self._repo.list(filters)
        logger.debug("Places listed: count=%d", len(places))
        return await self.reads(places)

    async def default_city_id(self) -> int:
        """The city a place gets when none is given: the Home place's."""
        home = await self._repo.get_home()
        if home is None:
            raise LocationValidationError("city_id is required: there is no Home place to take the city from")
        return home.city_id

    async def find(self, ref: str, city_id: int | None = None) -> Place | None:
        """A place by id (digits) or by name (case-insensitive) in `city_id` (default: the Home place's city).

        Several places of that name across cities, with no city given and none in the home city, is a 409 listing them.
        """
        ref = ref.strip()
        if ref.isdigit():
            return await self._repo.get(int(ref))
        if city_id is None:
            home = await self._repo.get_home()
            if home is not None:
                in_home_city = await self._repo.get_by_name(ref, home.city_id)
                if in_home_city:
                    return in_home_city[0]
            matches = await self._repo.get_by_name(ref)
        else:
            matches = await self._repo.get_by_name(ref, city_id)
        if len(matches) > 1:
            candidates = ", ".join(f"{p.name} in {p.city.name} (id {p.id})" for p in matches)
            raise LocationConflictError(f"Several places are called {ref!r}: {candidates}. Use the id or --city")
        return matches[0] if matches else None

    async def _check_clashes(self, name: str, kind: str, city_id: int, place_id: int | None) -> None:
        for other in await self._repo.get_by_name(name, city_id):
            if other.id != place_id:
                raise LocationConflictError(
                    f"A place named {other.name!r} already exists in {other.city.name} (id {other.id})"
                )
        if kind == HOME_KIND:
            home = await self._repo.get_home()
            if home is not None and home.id != place_id:
                raise LocationConflictError(f"Home is already set: {home.name!r} (id {home.id})")

    async def _require_city(self, city_id: int) -> None:
        if not await self._repo.city_exists(city_id):
            raise LocationNotFoundError(f"City {city_id} not found")

    async def _commit(self) -> None:
        # The service checks name and home clashes first; this catches a race between two writes.
        try:
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise LocationConflictError("Another place already has this name in that city, or a home already exists") from exc

    async def add(self, data: PlaceCreate) -> Place:
        """Insert the place without committing, so a caller can add its own rows (an everyday membership) first."""
        city_id = data.city_id if data.city_id is not None else await self.default_city_id()
        await self._require_city(city_id)
        await self._check_clashes(data.name, data.kind, city_id, None)
        fields = data.model_dump(exclude={"coordinates"})
        fields["city_id"] = city_id
        fields["opening_hours"] = _hours(data.opening_hours)
        fields.update(_coordinate_fields(data.coordinates, data.maps_url))
        return await self._repo.add(fields)

    async def saved(self, place_id: int, created: bool) -> PlaceRead:
        """Commit a create (from `add`) or update, tell the hooks, and return the place as read."""
        await self._commit()
        place = await self._repo.get(place_id)
        assert place is not None
        if created:
            logger.info("Place created: id=%d name=%r kind=%s city_id=%d", place.id, place.name, place.kind, place.city_id)
        for hook in self._hooks:
            await hook.place_saved(place)
        return await self._read(place)

    async def create(self, data: PlaceCreate) -> PlaceRead:
        place = await self.add(data)
        return await self.saved(place.id, created=True)

    async def update(self, place_id: int, data: PlaceUpdate) -> PlaceRead | None:
        changes = data.model_dump(exclude_unset=True)
        for field in _REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise LocationValidationError(f"{field} cannot be cleared")
        current = await self._repo.get(place_id)
        if current is None:
            logger.debug("Place update: id=%d not found", place_id)
            return None
        if "city_id" in changes:
            await self._require_city(changes["city_id"])
        if changes.keys() & {"name", "kind", "city_id"}:
            await self._check_clashes(
                changes.get("name", current.name), changes.get("kind", current.kind),
                changes.get("city_id", current.city_id), place_id,
            )
        old_home = _home_values(current.kind, current.address, current.city_id)
        new_home = _home_values(
            changes.get("kind", current.kind), changes.get("address", current.address),
            changes.get("city_id", current.city_id),
        )
        if "opening_hours" in changes:
            changes["opening_hours"] = _hours(changes["opening_hours"])
        if "coordinates" in changes:
            changes.update(_coordinate_fields(changes.pop("coordinates"), changes.get("maps_url", current.maps_url)))
        elif current.latitude is None and changes.get("maps_url"):
            # No coordinates yet: a new Maps link that carries some fills them.
            changes.update(_coordinate_fields(None, changes["maps_url"]))
        await self._keep_old_home(old_home, new_home)
        await self._repo.update(current, changes)
        logger.info("Place updated: id=%d name=%r fields=%s", place_id, current.name, list(changes))
        return await self.saved(place_id, created=False)

    async def delete(self, place_id: int) -> bool:
        place = await self._repo.get(place_id)
        if place is None:
            logger.debug("Place delete: id=%d not found", place_id)
            return False
        reasons = [reason for hook in self._hooks if (reason := await hook.place_in_use(place))]
        if reasons:
            raise LocationConflictError(f"{place.name!r} can't be deleted: {'; '.join(reasons)}. Archive it instead")
        name, kind, old_home = place.name, place.kind, _home_values(place.kind, place.address, place.city_id)
        after = [await hook.before_place_delete(place_id) for hook in self._hooks]
        await self._keep_old_home(old_home, HomeValues())
        try:
            await self._repo.delete(place)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            raise LocationConflictError(f"{name!r} is still in use; archive it instead") from exc
        logger.info("Place deleted: id=%d name=%r kind=%s", place_id, name, kind)
        for run in after:
            await run()
        return True
