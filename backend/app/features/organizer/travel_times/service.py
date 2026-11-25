import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.errors import LocationValidationError
from app.features.location.places.constants import HOME_KIND
from app.features.location.places.repository import normalized
from app.features.location.places.service import PlaceService
from app.features.location.places.tables import Place
from app.features.organizer.everyday_places.schemas import EverydayPlaceCreate
from app.features.organizer.everyday_places.service import EverydayPlaceService
from app.features.organizer.travel_times.repository import TravelTimeRepository
from app.features.organizer.travel_times.schemas import MAX_TRAVEL_TIMES, TravelTimeRead, TravelTimeSet
from app.features.organizer.travel_times.tables import TravelTime

logger = logging.getLogger(__name__)

# A name typed in a travel time that is not a place yet becomes an everyday place; these names get a fitting kind.
_GUESSED_KINDS = {"office": "work", "work": "work", "school": "school", "gym": "gym"}


def route_name(place: Place) -> str:
    """How travel times name a place for planning: "home" for the home, else its name in lowercase."""
    return HOME_KIND if place.kind == HOME_KIND else place.name.lower()


def route_label(travel_time: TravelTime) -> str:
    return (
        f"{travel_time.origin.name} → {travel_time.destination.name} by {travel_time.mode} "
        f"({travel_time.minutes} min)"
    )


@dataclass(frozen=True)
class TravelNetwork:
    """Every place's name (archived ones too: past events may sit there) and every route between them."""

    names: dict[int, str]
    home_id: int | None
    # (origin id, destination id, mode, minutes)
    routes: list[tuple[int, int, str, int]]


class TravelTimeService:
    """Door-to-door minutes between places: set from a place's page or command, or all at once from the
    planning settings (the old `planning.travel_times` syntax, which keeps working on top of these rows)."""

    def __init__(self, session: AsyncSession, places: PlaceService) -> None:
        self._repo = TravelTimeRepository(session)
        self._places = places
        self._everyday = EverydayPlaceService(session, places)

    async def list_for(self, place_id: int) -> list[TravelTimeRead] | None:
        if await self._places.get_row(place_id) is None:
            return None
        return [TravelTimeRead.model_validate(t) for t in await self._repo.list_for(place_id)]

    async def set(self, origin_id: int, data: TravelTimeSet) -> TravelTimeRead | None:
        """Save the minutes from one place to another by one mode; an existing route is updated."""
        if await self._places.get_row(origin_id) is None:
            return None
        if data.destination_id == origin_id:
            raise LocationValidationError("A place cannot be travelled to from itself")
        if await self._places.get_row(data.destination_id) is None:
            raise LocationValidationError(f"Unknown place id {data.destination_id}")
        if await self._repo.find(origin_id, data.destination_id, data.mode) is None:
            if await self._repo.count() >= MAX_TRAVEL_TIMES:
                raise LocationValidationError(f"At most {MAX_TRAVEL_TIMES} travel times; delete one first")
        saved = await self._repo.save(origin_id, data.destination_id, data.mode, data.minutes)
        logger.info(
            "Travel time saved: id=%d origin_place_id=%d destination_place_id=%d mode=%s",
            saved.id, origin_id, data.destination_id, data.mode,
        )
        return TravelTimeRead.model_validate(saved)

    async def delete(self, travel_time_id: int) -> bool:
        travel_time = await self._repo.get(travel_time_id)
        if travel_time is None:
            logger.debug("Travel time delete: id=%d not found", travel_time_id)
            return False
        await self._repo.delete(travel_time)
        logger.info("Travel time deleted: id=%d", travel_time_id)
        return True

    async def network(self) -> TravelNetwork:
        """What the day plan needs to name events' places and tell which have a travel time."""
        home = await self._places.get_home()
        return TravelNetwork(
            names=await self._places.names(),
            home_id=home.id if home else None,
            routes=[(t.origin_place_id, t.destination_place_id, t.mode, t.minutes) for t in await self._repo.list_all()],
        )

    async def as_preferences(self) -> list[dict]:
        """Every travel time as the planning preferences list: [{origin, place, mode, minutes}], names lowercase."""
        return [
            {"origin": route_name(t.origin), "place": route_name(t.destination), "mode": t.mode, "minutes": t.minutes}
            for t in await self._repo.list_all()
        ]

    async def replace_from_preferences(self, entries: Iterable[tuple[str, str, str, int]]) -> None:
        """Replace every travel time with (origin, place, mode, minutes) entries named as in the planning settings.

        "home" is the Home place; any other name the everyday place of that name (case-insensitive), else a place of
        that name in the home city, created as an everyday place when missing. The caller validates the entries
        (distinct ends, no duplicates, at most MAX_TRAVEL_TIMES).
        """
        ids: dict[str, int] = {}
        routes = []
        for origin, place, mode, minutes in entries:
            for name in (origin, place):
                if name not in ids:
                    ids[name] = await self._place_id(name)
            routes.append((ids[origin], ids[place], mode, minutes))
        await self._repo.replace_all(routes)
        logger.info("Travel times replaced from the planning settings: count=%d", len(routes))

    async def find_place(self, name: str) -> Place | None:
        """The place a route name means: "home" is the Home place, else the everyday place (then any place in the
        home city) with that name."""
        name = normalized(name)
        if name == HOME_KIND:
            home = await self._places.get_home()
            if home is not None:
                return await self._places.get_row(home.id)
        found = await self._everyday.find(name)
        return None if found is None else await self._places.get_row(found.id)

    async def _place_id(self, name: str) -> int:
        place = await self.find_place(name)
        if place is not None:
            return place.id
        kind = HOME_KIND if name == HOME_KIND else _GUESSED_KINDS.get(name, "other")
        created = await self._everyday.create(EverydayPlaceCreate(name=name[:1].upper() + name[1:], kind=kind))
        logger.info("Everyday place created from a travel time: id=%d kind=%s", created.id, kind)
        return created.id

