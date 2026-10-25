from datetime import datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import LocalDateTime
from app.features.organizer.tags.tables import Tag, activities_tags
from app.features.organizer.tasks.schemas import TASK_CONTEXTS


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint("min_minutes > 0", name="ck_activities_min_minutes"),
        CheckConstraint("max_minutes > 0", name="ck_activities_max_minutes"),
        CheckConstraint(
            "max_minutes IS NULL OR min_minutes IS NULL OR max_minutes >= min_minutes", name="ck_activities_min_max"
        ),
        CheckConstraint("target_per_week > 0", name="ck_activities_target_per_week"),
        CheckConstraint(
            "context IN ({})".format(", ".join(f"'{c}'" for c in TASK_CONTEXTS)), name="ck_activities_context"
        ),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    min_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    target_per_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[List[Tag]] = relationship("Tag", secondary=activities_tags, back_populates="activities")


class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = (
        CheckConstraint("minutes > 0", name="ck_activity_logs_minutes"),
        Index("ix_activity_logs_activity_done_at", "activity_id", "done_at"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # RESTRICT: archiving an activity keeps its logs; an activity with logs is never hard-deleted.
    activity_id: Mapped[int] = mapped_column(ForeignKey("organizer.activities.id", ondelete="RESTRICT"), nullable=False)
    done_at: Mapped[datetime] = mapped_column(LocalDateTime, nullable=False)
    minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
