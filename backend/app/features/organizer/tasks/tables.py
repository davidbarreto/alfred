from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship, Mapped, mapped_column, validates
from typing import Optional, List
from datetime import date, datetime, timezone

from app.features.organizer.tags.tables import Tag
from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_tasks_provider_id"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(255), nullable=False)
    urgency: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.tasks_tags",
        back_populates="tasks",
    )
    completions: Mapped[List["TaskCompletion"]] = relationship(
        "TaskCompletion",
        back_populates="task",
        cascade="all, delete-orphan",
    )

    @validates("status")
    def _sync_completed_at(self, key: str, value: str) -> str:
        # Runs on every status write, not just TaskService.complete_task -- so a task
        # closed via a plain field update (e.g. PATCH or /taskupdate -s DONE) still gets
        # completed_at set, and reopening a DONE task clears the stale timestamp.
        if value == "DONE" and self.status != "DONE":
            self.completed_at = datetime.now(timezone.utc)
        elif value != "DONE" and self.status == "DONE":
            self.completed_at = None
        return value


class TaskCompletion(Base):
    __tablename__ = "task_completions"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("organizer.tasks.id", ondelete="CASCADE"), nullable=False)
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped["Task"] = relationship("Task", back_populates="completions")
