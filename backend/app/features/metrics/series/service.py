import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.series.repository import MetricSeriesRepository
from app.features.metrics.series.schemas import (
    MetricSeriesCreate,
    MetricSeriesMerge,
    MetricSeriesRead,
    MetricSeriesSummary,
    MetricSeriesUpdate,
)

logger = logging.getLogger(__name__)


class MetricSeriesNameTakenError(Exception):
    """A series with that name already exists."""


class MetricSeriesNotEmptyError(Exception):
    """The series still has entries; archive it or merge it into another series instead."""

    def __init__(self, entry_count: int):
        super().__init__(f"Series has {entry_count} entries")
        self.entry_count = entry_count


class MetricSeriesMergeError(Exception):
    """The series can't be merged (same series, or different kinds)."""


class MetricSeriesService:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = MetricSeriesRepository(session)

    async def get_all_series(self, include_archived: bool = False) -> list[MetricSeriesSummary]:
        rows = await self._repo.get_all_series(include_archived=include_archived)
        return [
            MetricSeriesSummary(**MetricSeriesRead.model_validate(series).model_dump(), entry_count=count)
            for series, count in rows
        ]

    async def get_series(self, name: str) -> MetricSeriesRead | None:
        series = await self._repo.get_series_by_name(name)
        return MetricSeriesRead.model_validate(series) if series else None

    async def create_series(self, data: MetricSeriesCreate) -> MetricSeriesRead:
        if await self._repo.get_series_by_name(data.name) is not None:
            raise MetricSeriesNameTakenError(data.name)
        try:
            series = await self._repo.create_series(data.name, data.kind, data.unit, data.description)
        except IntegrityError as exc:
            await self._session.rollback()
            raise MetricSeriesNameTakenError(data.name) from exc
        logger.info("Metric series created: id=%d name=%r kind=%s", series.id, series.name, series.kind)
        return MetricSeriesRead.model_validate(series)

    async def update_series(self, name: str, data: MetricSeriesUpdate) -> MetricSeriesRead | None:
        series = await self._repo.get_series_by_name(name)
        if series is None:
            logger.debug("Metric series update: name=%r not found", name)
            return None
        changes = data.model_dump(exclude_unset=True)
        new_name = changes.get("name")
        if new_name is not None and new_name != series.name and await self._repo.get_series_by_name(new_name):
            raise MetricSeriesNameTakenError(new_name)
        series_id = series.id
        try:
            updated = await self._repo.update_series(series_id, changes)
        except IntegrityError as exc:
            await self._session.rollback()
            raise MetricSeriesNameTakenError(str(new_name)) from exc
        assert updated is not None
        logger.info("Metric series updated: id=%d fields=%s", series_id, list(changes))
        return MetricSeriesRead.model_validate(updated)

    async def merge_series(self, name: str, data: MetricSeriesMerge) -> MetricSeriesRead | None:
        """Move every entry of `name` into `data.into`, then remove the (now empty) source series."""
        source = await self._repo.get_series_by_name(name)
        target = await self._repo.get_series_by_name(data.into)
        if source is None or target is None:
            logger.debug("Metric series merge: %r or %r not found", name, data.into)
            return None
        if source.id == target.id or source.kind != target.kind:
            raise MetricSeriesMergeError(f"Cannot merge {source.name} ({source.kind}) into {target.name} ({target.kind})")
        source_id, source_name, target_id = source.id, source.name, target.id
        moved = await self._repo.move_entries(source_id, target_id)
        await self._repo.delete_series(source_id)
        logger.info("Metric series merged: from=%r into=%r entries=%d", source_name, data.into, moved)
        return MetricSeriesRead.model_validate(target)

    async def delete_series(self, name: str) -> bool:
        series = await self._repo.get_series_by_name(name)
        if series is None:
            return False
        count = await self._repo.count_entries(series.id)
        if count:
            raise MetricSeriesNotEmptyError(count)
        series_id = series.id
        deleted = await self._repo.delete_series(series_id)
        if deleted:
            logger.info("Metric series deleted: id=%d name=%r", series_id, name)
        return deleted
