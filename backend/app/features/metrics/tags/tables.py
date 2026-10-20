from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# RESTRICT on both sides: entries are discarded, never hard-deleted, and a tag in use can't vanish.
metric_entry_tag_links = Table(
    "entries_tags",
    Base.metadata,
    Column("entry_id", ForeignKey("metrics.entries.id", ondelete="RESTRICT"), primary_key=True),
    Column("tag_id", ForeignKey("metrics.tags.id", ondelete="RESTRICT"), primary_key=True, index=True),
    schema="metrics",
)


class MetricTag(Base):
    __tablename__ = "tags"
    __table_args__ = {"schema": "metrics"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Names are unique ignoring case so "Bus" and "bus" can't coexist.
Index("uq_metric_tags_name_lower", func.lower(MetricTag.name), unique=True)
