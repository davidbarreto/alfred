from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.organizer.tags.tables import Tag


class CalendarEventInvitee(Base):
    __tablename__ = "calendar_event_invitees"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    event: Mapped["CalendarEvent"] = relationship("CalendarEvent", back_populates="invitees")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_calendar_events_provider_id"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    invitees: Mapped[List["CalendarEventInvitee"]] = relationship(
        "CalendarEventInvitee",
        back_populates="event",
        cascade="all, delete-orphan",
    )
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.calendar_events_tags",
        back_populates="calendar_events",
    )
