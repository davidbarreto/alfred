from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.interviews.processes.tables import InterviewProcess

interview_stage_contacts = Table(
    "interview_stage_contacts",
    Base.metadata,
    Column("stage_id", Integer, ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"), primary_key=True),
    Column("contact_id", Integer, ForeignKey("organizer.contacts.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(50), nullable=True),
    schema="organizer",
)

interview_stage_tasks = Table(
    "interview_stage_tasks",
    Base.metadata,
    Column("stage_id", Integer, ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"), primary_key=True),
    Column("task_id", Integer, ForeignKey("organizer.tasks.id", ondelete="CASCADE"), primary_key=True),
    schema="organizer",
)

interview_stage_notes = Table(
    "interview_stage_notes",
    Base.metadata,
    Column("stage_id", Integer, ForeignKey("organizer.interview_stages.id", ondelete="CASCADE"), primary_key=True),
    Column("note_id", Integer, ForeignKey("organizer.notes.id", ondelete="CASCADE"), primary_key=True),
    schema="organizer",
)


class InterviewStage(Base):
    __tablename__ = "interview_stages"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scheduled_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="scheduled")
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calendar_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizer.calendar_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    process: Mapped["InterviewProcess"] = relationship("InterviewProcess", back_populates="stages")
