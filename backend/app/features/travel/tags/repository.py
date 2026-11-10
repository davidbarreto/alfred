from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.tags.tables import TravelTag, places_tags, trips_tags


class TravelTagRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_tag(self, tag_id: int) -> TravelTag | None:
        return await self._session.get(TravelTag, tag_id)

    async def get_tag_by_name(self, name: str) -> TravelTag | None:
        stmt = select(TravelTag).where(func.lower(TravelTag.name) == name.lower())
        return await self._session.scalar(stmt)

    async def get_or_create_tags(self, names: list[str]) -> list[TravelTag]:
        """Resolve names (case-insensitively) to tags, creating missing ones. Does not commit."""
        tags: list[TravelTag] = []
        for name in names:
            tag = await self.get_tag_by_name(name)
            if tag is None:
                tag = TravelTag(name=name)
                self._session.add(tag)
                await self._session.flush()
            tags.append(tag)
        return tags

    async def get_tags_with_usage(self) -> list[tuple[TravelTag, int, int]]:
        trip_counts = (
            select(trips_tags.c.tag_id, func.count().label("n")).group_by(trips_tags.c.tag_id).subquery()
        )
        place_counts = (
            select(places_tags.c.tag_id, func.count().label("n")).group_by(places_tags.c.tag_id).subquery()
        )
        stmt = (
            select(TravelTag, func.coalesce(trip_counts.c.n, 0), func.coalesce(place_counts.c.n, 0))
            .outerjoin(trip_counts, trip_counts.c.tag_id == TravelTag.id)
            .outerjoin(place_counts, place_counts.c.tag_id == TravelTag.id)
            .order_by(func.lower(TravelTag.name))
        )
        return [(tag, trips, places) for tag, trips, places in (await self._session.execute(stmt)).all()]

    async def rename_tag(self, tag_id: int, name: str) -> TravelTag | None:
        tag = await self.get_tag(tag_id)
        if tag is None:
            return None
        tag.name = name
        await self._session.commit()
        return tag

    async def delete_tag(self, tag_id: int) -> bool:
        """Removes the tag and (by CASCADE) only its link rows."""
        result = await self._session.execute(delete(TravelTag).where(TravelTag.id == tag_id))
        await self._session.commit()
        return result.rowcount > 0
