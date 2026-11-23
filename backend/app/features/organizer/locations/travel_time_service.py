from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.locations.errors import LocationValidationError
from app.features.organizer.locations.repository import LocationRepository
from app.features.organizer.locations.schemas import (
    MAX_TRAVEL_TIMES,
    LocationFilters,
    LocationTravelTimeRead,
    LocationTravelTimeSet,
)
from app.features.organizer.locations.tables import HOME_KIND, Location, LocationTravelTime
from app.features.organizer.locations.travel_time_repository import LocationTravelTimeRepository

logger = logging.getLogger(__name__)

# A name typed in a travel time that is not a location yet becomes one; these names get a fitting kind.
_GUESSED_KINDS = {"office": "work", "work": "work", "school": "school", "gym": "gym"}


def route_name(location: Location) -> str:
    """How travel times name a location for planning: "home" for the home, else its name in lowercase."""
    return HOME_KIND if location.kind == HOME_KIND else location.name.lower()


def route_label(travel_time: LocationTravelTime) -> str:
    return (
        f"{travel_time.origin.name} → {travel_time.destination.name} by {travel_time.mode} "
        f"({travel_time.minutes} min)"
    )


@dataclass(frozen=True)
class TravelNetwork:
    """Every location's name (archived ones too: past events may sit there) and every route between them."""

    names: dict[int, str]
    home_id: int | None
    # (origin id, destination id, mode, minutes)
    routes: list[tuple[int, int, str, int]]


class LocationTravelTimeService:
    """Door-to-door minutes between locations: set from a location's page or command, or all at once from the
    planning settings (the old `planning.travel_times` syntax, which keeps working on top of these rows)."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = LocationTravelTimeRepository(session)
        self._locations = LocationRepository(session)

    async def list_for(self, location_id: int) -> list[LocationTravelTimeRead] | None:
        if await self._locations.get(location_id) is None:
            return None
        return [LocationTravelTimeRead.model_validate(t) for t in await self._repo.list_for(location_id)]

    async def set(self, origin_id: int, data: LocationTravelTimeSet) -> LocationTravelTimeRead | None:
        """Save the minutes from one location to another by one mode; an existing route is updated."""
        if await self._locations.get(origin_id) is None:
            return None
        if data.destination_id == origin_id:
            raise LocationValidationError("A location cannot be travelled to from itself")
        if await self._locations.get(data.destination_id) is None:
            raise LocationValidationError(f"Unknown location id {data.destination_id}")
        if await self._repo.find(origin_id, data.destination_id, data.mode) is None:
            if await self._repo.count() >= MAX_TRAVEL_TIMES:
                raise LocationValidationError(f"At most {MAX_TRAVEL_TIMES} travel times; delete one first")
        saved = await self._repo.save(origin_id, data.destination_id, data.mode, data.minutes)
        logger.info(
            "Location travel time saved: id=%d origin_id=%d destination_id=%d mode=%s",
            saved.id, origin_id, data.destination_id, data.mode,
        )
        return LocationTravelTimeRead.model_validate(saved)

    async def delete(self, travel_time_id: int) -> bool:
        travel_time = await self._repo.get(travel_time_id)
        if travel_time is None:
            logger.debug("Location travel time delete: id=%d not found", travel_time_id)
            return False
        await self._repo.delete(travel_time)
        logger.info("Location travel time deleted: id=%d", travel_time_id)
        return True

    async def network(self) -> TravelNetwork:
        """What the day plan needs to derive travel between events' locations, in two queries."""
        locations = await self._locations.list(LocationFilters(limit=500))
        home = next((loc.id for loc in locations if loc.kind == HOME_KIND), None)
        return TravelNetwork(
            names={loc.id: loc.name for loc in locations},
            home_id=home,
            routes=[(t.origin_id, t.destination_id, t.mode, t.minutes) for t in await self._repo.list_all()],
        )

    async def as_preferences(self) -> list[dict]:
        """Every travel time as the planning preferences list: [{origin, place, mode, minutes}], names lowercase."""
        return [
            {"origin": route_name(t.origin), "place": route_name(t.destination), "mode": t.mode, "minutes": t.minutes}
            for t in await self._repo.list_all()
        ]

    async def replace_from_preferences(self, entries: Iterable[tuple[str, str, str, int]]) -> None:
        """Replace every travel time with (origin, place, mode, minutes) entries named as in the planning settings.

        "home" is the home location; any other name the location of that name (case-insensitive), created when
        missing. The caller validates the entries (distinct ends, no duplicates, at most MAX_TRAVEL_TIMES).
        """
        ids: dict[str, int] = {}
        routes = []
        for origin, place, mode, minutes in entries:
            for name in (origin, place):
                if name not in ids:
                    ids[name] = await self._location_id(name)
            routes.append((ids[origin], ids[place], mode, minutes))
        await self._repo.replace_all(routes)
        logger.info("Location travel times replaced from the planning settings: count=%d", len(routes))

    async def find_location(self, name: str) -> Location | None:
        """The location a route name means: "home" is the home location, else the location with that name."""
        name = " ".join(name.split()).lower()
        if name == HOME_KIND:
            home = await self._locations.get_home()
            if home is not None:
                return home
        return await self._locations.get_by_name(name)

    async def _location_id(self, name: str) -> int:
        location = await self.find_location(name)
        if location is not None:
            return location.id
        kind = HOME_KIND if name == HOME_KIND else _GUESSED_KINDS.get(name, "other")
        created = await self._locations.create({"name": name[:1].upper() + name[1:], "kind": kind}, [])
        logger.info("Location created from a travel time: id=%d name=%r kind=%s", created.id, created.name, kind)
        return created.id
