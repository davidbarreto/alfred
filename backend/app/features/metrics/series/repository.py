from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.metrics.entries.tables import MetricEntry
from app.features.metrics.series.tables import MetricSeries


class MetricSeriesRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_series(self, series_id: int) -> MetricSeries | None:
        return await self._session.get(MetricSeries, series_id)

    async def get_series_by_name(self, name: str) -> MetricSeries | None:
        return await self._session.scalar(select(MetricSeries).where(MetricSeries.name == name))

    async def get_all_series(self, include_archived: bool = False) -> list[tuple[MetricSeries, int]]:
        counts = (
            select(MetricEntry.series_id, func.count().label("n"))
            .where(MetricEntry.status != "discarded")
            .group_by(MetricEntry.series_id)
            .subquery()
        )
        stmt = select(MetricSeries, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.series_id == MetricSeries.id)
        if not include_archived:
            stmt = stmt.where(MetricSeries.is_archived.is_(False))
        stmt = stmt.order_by(MetricSeries.name)
        return [(series, n) for series, n in (await self._session.execute(stmt)).all()]

    async def create_series(
        self, name: str, kind: str, unit: str | None = None, description: str | None = None
    ) -> MetricSeries:
        series = MetricSeries(name=name, kind=kind, unit=unit, description=description)
        self._session.add(series)
        await self._session.commit()
        return series

    async def update_series(self, series_id: int, fields: dict[str, Any]) -> MetricSeries | None:
        series = await self.get_series(series_id)
        if series is None:
            return None
        for key, value in fields.items():
            setattr(series, key, value)
        await self._session.commit()
        return series

    async def count_entries(self, series_id: int) -> int:
        stmt = select(func.count()).select_from(MetricEntry).where(MetricEntry.series_id == series_id)
        return int(await self._session.scalar(stmt) or 0)

    async def move_entries(self, from_series_id: int, to_series_id: int) -> int:
        result = await self._session.execute(
            update(MetricEntry).where(MetricEntry.series_id == from_series_id).values(series_id=to_series_id)
        )
        await self._session.commit()
        return result.rowcount

    async def delete_series(self, series_id: int) -> bool:
        """Only succeeds for a series with no entries (FK is RESTRICT)."""
        result = await self._session.execute(delete(MetricSeries).where(MetricSeries.id == series_id))
        await self._session.commit()
        return result.rowcount > 0
