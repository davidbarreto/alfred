from __future__ import annotations

import logging
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.errors import LocationConflictError, LocationValidationError
from app.features.location.places.constants import HOME_KIND
from app.features.location.places.repository import normalized
from app.features.location.places.schemas import PlaceCreate, PlaceUpdate
from app.features.location.places.service import PlaceService
from app.features.location.places.tables import Place
from app.features.organizer.everyday_places.repository import EverydayPlaceRepository
from app.features.organizer.everyday_places.schemas import (
    EverydayPlaceCreate,
    EverydayPlaceFilters,
    EverydayPlaceRead,
    PlaceCategory,
)
from app.features.organizer.shopping_categories.tables import ShoppingCategory

logger = logging.getLogger(__name__)


class EverydayPlaceService:
    """The everyday role of places: which ones are everyday (Home always is) and what each sells.

    What a place is (name, hours, coordinates, deleting it) goes through location's `PlaceService`.
    """

    def __init__(self, session: AsyncSession, places: PlaceService) -> None:
        self._repo = EverydayPlaceRepository(session)
        self._places = places

    async def _reads(self, places: Sequence[Place]) -> list[EverydayPlaceRead]:
        ids = [p.id for p in places]
        members = await self._repo.members(ids)
        categories = await self._repo.categories_of(ids)
        return [
            EverydayPlaceRead(
                **base.model_dump(exclude={"opening_hours_text", "maps_link"}),
                everyday=place.kind == HOME_KIND or place.id in members,
                categories=[PlaceCategory.model_validate(c) for c in categories.get(place.id, [])],
            )
            for place, base in zip(places, await self._places.reads(places))
        ]

    async def _read(self, place: Place) -> EverydayPlaceRead:
        return (await self._reads([place]))[0]

    async def _place(self, place_id: int) -> Place | None:
        return await self._places.get_row(place_id)

    async def list(self, filters: EverydayPlaceFilters) -> list[EverydayPlaceRead]:
        return await self._reads(await self._repo.list(filters))

    async def get(self, place_id: int) -> EverydayPlaceRead | None:
        """Any place as the everyday role sees it (`everyday` false when it is not one)."""
        place = await self._place(place_id)
        return None if place is None else await self._read(place)

    async def find(self, ref: str) -> EverydayPlaceRead | None:
        """A place by id or name: an everyday place of that name first, then any place in the home city."""
        ref = ref.strip()
        if not ref.isdigit():
            wanted = normalized(ref)
            for place in await self._repo.list(EverydayPlaceFilters(limit=500)):
                if place.name.lower() == wanted:
                    return await self._read(place)
        place = await self._places.find(ref)
        return None if place is None else await self._read(place)

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

    async def create(self, data: EverydayPlaceCreate) -> EverydayPlaceRead:
        """A new place that is everyday from the start (Home needs no membership row)."""
        categories = await self._categories(data.category_ids)
        place = await self._places.add(PlaceCreate(**data.model_dump(exclude={"category_ids"})))
        if place.kind != HOME_KIND:
            await self._repo.add_member(place.id)
        await self._repo.set_categories(place.id, [c.id for c in categories])
        await self._places.saved(place.id, created=True)
        logger.info("Everyday place created: place_id=%d categories=%d", place.id, len(categories))
        return await self._read(await self._require(place.id))

    async def update(
        self, place_id: int, data: PlaceUpdate, category_ids: list[int] | None = None
    ) -> EverydayPlaceRead | None:
        """Change the place and, when given, replace what it sells."""
        if data.model_fields_set:
            if await self._places.update(place_id, data) is None:
                return None
        elif await self._place(place_id) is None:
            return None
        if category_ids is not None:
            await self.set_categories(place_id, category_ids)
        return await self.get(place_id)

    async def add(self, place_id: int) -> EverydayPlaceRead | None:
        """Make the place one of the everyday places; adding it again changes nothing."""
        place = await self._place(place_id)
        if place is None:
            return None
        if place.kind != HOME_KIND and await self._repo.add_member(place_id):
            await self._repo.commit()
            logger.info("Everyday place added: place_id=%d", place_id)
        return await self._read(place)

    async def remove(self, place_id: int) -> bool:
        """Take the place off the everyday list (the place itself stays). False when the place does not exist."""
        place = await self._place(place_id)
        if place is None:
            return False
        if place.kind == HOME_KIND:
            raise LocationConflictError("Home is always an everyday place")
        if await self._repo.remove_member(place_id):
            await self._repo.commit()
            logger.info("Everyday place removed: place_id=%d", place_id)
        return True

    async def delete(self, place_id: int) -> bool:
        """Delete the place itself (location's rules: a 409 while travel times, visits or stays hold it)."""
        return await self._places.delete(place_id)

    async def get_categories(self, place_id: int) -> list[PlaceCategory] | None:
        if await self._place(place_id) is None:
            return None
        found = (await self._repo.categories_of([place_id])).get(place_id, [])
        return [PlaceCategory.model_validate(c) for c in found]

    async def set_categories(self, place_id: int, category_ids: list[int]) -> list[PlaceCategory] | None:
        if await self._place(place_id) is None:
            return None
        categories = await self._categories(category_ids)
        await self._repo.set_categories(place_id, [c.id for c in categories])
        await self._repo.commit()
        logger.info("Everyday place categories set: place_id=%d count=%d", place_id, len(categories))
        return await self.get_categories(place_id)

    async def _require(self, place_id: int) -> Place:
        place = await self._place(place_id)
        assert place is not None
        return place
