from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.tags.tables import MetricTag, metric_entry_tag_links


class MetricTagRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_tag(self, tag_id: int) -> MetricTag | None:
        return await self._session.get(MetricTag, tag_id)

    async def get_tag_by_name(self, name: str) -> MetricTag | None:
        stmt = select(MetricTag).where(func.lower(MetricTag.name) == name.lower())
        return await self._session.scalar(stmt)

    async def get_or_create_tags(self, names: list[str]) -> list[MetricTag]:
        """Resolve names (case-insensitively) to tags, creating missing ones. Does not commit."""
        tags: list[MetricTag] = []
        for name in names:
            tag = await self.get_tag_by_name(name)
            if tag is None:
                tag = MetricTag(name=name)
                self._session.add(tag)
                await self._session.flush()
            tags.append(tag)
        return tags

    async def get_tags_with_usage(self) -> list[tuple[MetricTag, int]]:
        counts = (
            select(metric_entry_tag_links.c.tag_id, func.count().label("n"))
            .group_by(metric_entry_tag_links.c.tag_id)
            .subquery()
        )
        stmt = (
            select(MetricTag, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.tag_id == MetricTag.id)
            .order_by(func.lower(MetricTag.name))
        )
        return [(tag, n) for tag, n in (await self._session.execute(stmt)).all()]

    async def count_usage(self, tag_id: int) -> int:
        stmt = select(func.count()).select_from(metric_entry_tag_links).where(metric_entry_tag_links.c.tag_id == tag_id)
        return int(await self._session.scalar(stmt) or 0)

    async def rename_tag(self, tag_id: int, name: str) -> MetricTag | None:
        tag = await self.get_tag(tag_id)
        if tag is None:
            return None
        tag.name = name
        await self._session.commit()
        return tag

    async def delete_tag(self, tag_id: int) -> bool:
        result = await self._session.execute(delete(MetricTag).where(MetricTag.id == tag_id))
        await self._session.commit()
        return result.rowcount > 0
