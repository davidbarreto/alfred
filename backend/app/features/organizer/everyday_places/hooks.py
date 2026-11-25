from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.hooks import AfterDelete
from app.features.location.places.tables import Place
from app.features.organizer.travel_times.repository import TravelTimeRepository
from app.features.organizer.travel_times.service import route_label


async def _nothing() -> None:
    return None


class OrganizerPlaceHooks:
    """Organizer's side of a place's life (`location.hooks.PlaceHooks`).

    Its everyday membership and shopping categories go with the place (CASCADE) and calendar events let go of it
    (SET NULL); only travel times hold it.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._travel_times = TravelTimeRepository(session)

    async def place_saved(self, place: Place) -> None:
        return None

    async def place_in_use(self, place: Place) -> str | None:
        travel_times = await self._travel_times.list_for(place.id)
        if not travel_times:
            return None
        routes = "; ".join(route_label(t) for t in travel_times[:5])
        more = f" and {len(travel_times) - 5} more" if len(travel_times) > 5 else ""
        return f"it has {len(travel_times)} travel time(s): {routes}{more}. Delete them first"

    async def before_place_delete(self, place_id: int) -> AfterDelete:
        return _nothing
