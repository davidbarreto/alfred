import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.study.tags.tables import StudyTag, plans_tags


class StudyPlan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("status IN ('backlog', 'active', 'completed', 'abandoned')", name="ck_study_plans_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_study_plans_priority"),
        {"schema": "study"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    track_id: Mapped[int] = mapped_column(
        ForeignKey("study.tracks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    activated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    items: Mapped[list["StudyPlanItem"]] = relationship(
        "StudyPlanItem", back_populates="plan", order_by="StudyPlanItem.position", cascade="all, delete-orphan"
    )
    tags: Mapped[list[StudyTag]] = relationship(StudyTag, secondary=plans_tags, order_by=StudyTag.name)


class StudyPlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('cs_tag', 'interview_stage', 'interview_process', 'story_gap', 'manual')",
            name="ck_study_plan_items_source_type",
        ),
        {"schema": "study"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("study.plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Why the item exists: source_id points at a row of the source_type's table (no FK, it's polymorphic).
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    plan: Mapped["StudyPlan"] = relationship("StudyPlan", back_populates="items")
