from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.tags.repository import MetricTagRepository
from app.features.metrics.tags.tables import MetricTag, metric_entry_tag_links


class MetricEntryRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._tags = MetricTagRepository(session)

    async def get_entry(self, entry_id: int) -> MetricEntry | None:
        stmt = select(MetricEntry).where(MetricEntry.id == entry_id).execution_options(populate_existing=True)
        return await self._session.scalar(stmt)

    async def get_entries(
        self,
        series_id: int | None = None,
        tag: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MetricEntry]:
        stmt = select(MetricEntry)
        if series_id is not None:
            stmt = stmt.where(MetricEntry.series_id == series_id)
        if status is not None:
            stmt = stmt.where(MetricEntry.status == status)
        if since is not None:
            stmt = stmt.where(MetricEntry.started_at >= since)
        if until is not None:
            stmt = stmt.where(MetricEntry.started_at < until)
        if tag is not None:
            tagged = (
                select(metric_entry_tag_links.c.entry_id)
                .join(MetricTag, MetricTag.id == metric_entry_tag_links.c.tag_id)
                .where(func.lower(MetricTag.name) == tag.lower())
            )
            stmt = stmt.where(MetricEntry.id.in_(tagged))
        stmt = stmt.order_by(MetricEntry.started_at.desc(), MetricEntry.id.desc()).limit(limit).offset(offset)
        return list((await self._session.scalars(stmt)).all())

    async def get_open_entries(self, series_id: int | None = None) -> list[MetricEntry]:
        """Open entries, most recently started first."""
        stmt = select(MetricEntry).where(MetricEntry.status == "open")
        if series_id is not None:
            stmt = stmt.where(MetricEntry.series_id == series_id)
        stmt = stmt.order_by(MetricEntry.started_at.desc(), MetricEntry.id.desc())
        return list((await self._session.scalars(stmt)).all())

    async def create_entry(self, fields: dict[str, Any], tags: list[str]) -> MetricEntry:
        entry = MetricEntry(**fields, tags=await self._tags.get_or_create_tags(tags))
        self._session.add(entry)
        await self._session.commit()
        refreshed = await self.get_entry(entry.id)
        assert refreshed is not None
        return refreshed

    async def update_entry(
        self, entry_id: int, fields: dict[str, Any], tags: list[str] | None = None
    ) -> MetricEntry | None:
        entry = await self.get_entry(entry_id)
        if entry is None:
            return None
        for name, value in fields.items():
            setattr(entry, name, value)
        if tags is not None:
            entry.tags = await self._tags.get_or_create_tags(tags)
        await self._session.commit()
        return await self.get_entry(entry_id)
