from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.metrics.series.tables import MetricSeries
from app.features.metrics.tags.tables import MetricTag, metric_entry_tag_links


class MetricEntry(Base):
    __tablename__ = "entries"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed', 'discarded')", name="ck_metric_entries_status"),
        CheckConstraint("source IN ('telegram', 'shortcut', 'portal', 'mcp')", name="ck_metric_entries_source"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_metric_entries_ended_after_start"),
        CheckConstraint(
            "(start_lat IS NULL OR start_lat BETWEEN -90 AND 90) AND (end_lat IS NULL OR end_lat BETWEEN -90 AND 90)"
            " AND (start_lon IS NULL OR start_lon BETWEEN -180 AND 180)"
            " AND (end_lon IS NULL OR end_lon BETWEEN -180 AND 180)",
            name="ck_metric_entries_coordinates",
        ),
        Index("ix_metric_entries_series_started", "series_id", "started_at"),
        Index("ix_metric_entries_open", "series_id", postgresql_where=text("status = 'open'")),
        {"schema": "metrics"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    series_id: Mapped[int] = mapped_column(ForeignKey("metrics.series.id", ondelete="RESTRICT"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    start_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    series: Mapped[MetricSeries] = relationship(lazy="selectin")
    tags: Mapped[list[MetricTag]] = relationship(secondary=metric_entry_tag_links, lazy="selectin")

    @property
    def series_name(self) -> str:
        return self.series.name

    @property
    def series_kind(self) -> str:
        return self.series.kind

    @property
    def duration_s(self) -> int | None:
        """Derived from the timestamps, never stored, so edits can't make it drift."""
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at).total_seconds())
