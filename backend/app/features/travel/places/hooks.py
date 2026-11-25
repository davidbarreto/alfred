from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.embeddings.service import EmbeddingService
from app.features.location.hooks import AfterDelete
from app.features.location.places.tables import Place
from app.features.travel.links.repository import WebLinkRepository
from app.features.travel.notes_index import PLACE_NOTE, WEB_LINK_NOTE, TravelNoteIndex
from app.features.travel.stays.tables import Stay
from app.features.travel.visits.tables import Visit


class TravelPlaceHooks:
    """Travel's side of a place's life (`location.hooks.PlaceHooks`): visits and stays hold it, its tags and links go
    with it, and its notes are indexed for recall."""

    def __init__(self, session: AsyncSession, embedding_service: EmbeddingService | None = None) -> None:
        self._session = session
        self._links = WebLinkRepository(session)
        self._notes = TravelNoteIndex(embedding_service)

    async def place_saved(self, place: Place) -> None:
        await self._notes.sync(PLACE_NOTE, place.id, place.name, place.notes)

    async def _count(self, model: type[Visit] | type[Stay], place_id: int) -> int:
        stmt = select(func.count()).select_from(model).where(model.place_id == place_id)
        return int(await self._session.scalar(stmt) or 0)

    async def place_in_use(self, place: Place) -> str | None:
        visits, stays = await self._count(Visit, place.id), await self._count(Stay, place.id)
        if not visits and not stays:
            return None
        return f"it has {visits} visit(s) and {stays} stay(s)"

    async def before_place_delete(self, place_id: int) -> AfterDelete:
        """Links go with the place (CASCADE); their note embeddings and the place's are dropped after the commit."""
        link_ids = await self._links.get_link_ids(place_id=place_id)

        async def _drop_notes() -> None:
            await self._notes.remove(PLACE_NOTE, place_id)
            for link_id in link_ids:
                await self._notes.remove(WEB_LINK_NOTE, link_id)

        return _drop_notes
