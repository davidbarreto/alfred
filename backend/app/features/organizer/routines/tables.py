from datetime import date, datetime, time
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.organizer.tasks.schemas import TASK_CONTEXTS


def _in(column: str, values: tuple[str, ...]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


class Routine(Base):
    __tablename__ = "routines"
    __table_args__ = (
        CheckConstraint("(recurrence_rule IS NULL) = (starts_on IS NULL)", name="ck_routines_rule_starts_on"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    starts_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    steps: Mapped[List["RoutineStep"]] = relationship(
        "RoutineStep",
        back_populates="routine",
        cascade="all, delete-orphan",
        order_by="RoutineStep.position",
    )


class RoutineStep(Base):
    __tablename__ = "routine_steps"
    __table_args__ = (
        UniqueConstraint("routine_id", "position", name="uq_routine_steps_routine_position"),
        CheckConstraint("duration_minutes >= 0", name="ck_routine_steps_duration"),
        CheckConstraint(_in("anchor", ("start", "end")), name="ck_routine_steps_anchor"),
        CheckConstraint(_in("context", TASK_CONTEXTS), name="ck_routine_steps_context"),
        CheckConstraint("window_end IS NULL OR window_end > window_start", name="ck_routine_steps_window_order"),
        CheckConstraint(
            "(anchor IS NOT NULL AND offset_minutes IS NOT NULL AND window_start IS NULL AND window_end IS NULL)"
            " OR (anchor IS NULL AND offset_minutes IS NULL AND window_start IS NOT NULL AND window_end IS NOT NULL)",
            name="ck_routine_steps_timing_form",
        ),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    routine_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.routines.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    anchor: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)
    offset_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    window_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    window_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checklist_note_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizer.notes.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    routine: Mapped["Routine"] = relationship("Routine", back_populates="steps")
