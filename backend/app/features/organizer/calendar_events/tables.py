from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import LocalDateTime
from app.features.organizer.calendar_events.constants import EVENT_AVAILABILITIES, EVENT_PRESENCES
from app.features.organizer.activities.tables import Activity  # noqa: F401 — Tag.activities needs Activity registered wherever Tag is mapped
from app.features.organizer.routines.tables import Routine  # noqa: F401 — registers Routine for the routine_id foreign key
from app.features.organizer.tags.tables import Tag


class CalendarEventSkip(Base):
    """One occurrence of a recurring event that the user will not attend. Alfred-only: Google is never told."""

    __tablename__ = "calendar_event_skips"
    __table_args__ = (
        UniqueConstraint("event_id", "occurrence_date", name="uq_calendar_event_skips_event_date"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    event: Mapped["CalendarEvent"] = relationship("CalendarEvent", back_populates="skips")


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
        CheckConstraint(
            "availability IS NULL OR availability IN ({})".format(", ".join(f"'{v}'" for v in EVENT_AVAILABILITIES)),
            name="ck_calendar_events_availability",
        ),
        CheckConstraint(
            "presence IN ({})".format(", ".join(f"'{v}'" for v in EVENT_PRESENCES)),
            name="ck_calendar_events_presence",
        ),
        CheckConstraint("travel_minutes >= 0", name="ck_calendar_events_travel_minutes"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    start_datetime: Mapped[datetime] = mapped_column(LocalDateTime, nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(LocalDateTime, nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    notification_profile: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Planning fields: Alfred-only, never sent to Google and never overwritten by sync.
    availability: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    presence: Mapped[str] = mapped_column(String(16), nullable=False, default="in_person", server_default="in_person")
    travel_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    routine_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizer.routines.id", ondelete="SET NULL"), nullable=True
    )

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
    skips: Mapped[List["CalendarEventSkip"]] = relationship(
        "CalendarEventSkip",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="CalendarEventSkip.occurrence_date",
    )
