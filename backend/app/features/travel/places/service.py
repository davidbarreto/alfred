import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.places.repository import PlaceRepository
from app.features.travel.places.schemas import PlaceCreate, PlaceFilters, PlaceRead, PlaceUpdate

logger = logging.getLogger(__name__)


class PlaceInUseError(Exception):
    """The place has visits or stays, so it can't be deleted."""


class PlaceService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = PlaceRepository(session)

    async def get_places(self, filters: PlaceFilters) -> list[PlaceRead]:
        places = await self._repo.get_places(filters)
        logger.debug("Places listed: count=%d", len(places))
        return [PlaceRead.model_validate(p) for p in places]

    async def get_place(self, place_id: int) -> PlaceRead | None:
        place = await self._repo.get_place(place_id)
        return PlaceRead.model_validate(place) if place else None

    async def create_place(self, data: PlaceCreate) -> PlaceRead:
        place = await self._repo.create_place(data.model_dump())
        logger.info("Place created: id=%d kind=%s name=%r", place.id, place.kind, place.name)
        return PlaceRead.model_validate(place)

    async def update_place(self, place_id: int, data: PlaceUpdate) -> PlaceRead | None:
        changes = data.model_dump(exclude_unset=True)
        for required in ("kind", "name"):
            if required in changes and changes[required] is None:
                raise ValueError(f"{required} cannot be null")
        place = await self._repo.update_place(place_id, changes)
        if place is None:
            logger.debug("Place update: id=%d not found", place_id)
            return None
        logger.info("Place updated: id=%d fields=%s", place_id, list(changes.keys()))
        return PlaceRead.model_validate(place)

    async def delete_place(self, place_id: int) -> bool:
        try:
            deleted = await self._repo.delete_place(place_id)
        except IntegrityError as exc:
            await self._session.rollback()
            raise PlaceInUseError(place_id) from exc
        if deleted:
            logger.info("Place deleted: id=%d", place_id)
        return deleted
