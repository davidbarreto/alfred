from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.travel.cities.tables import City
from app.features.travel.constants import LEG_MODES, in_clause


class Leg(Base):
    __tablename__ = "legs"
    __table_args__ = (
        CheckConstraint(in_clause("mode", LEG_MODES), name="ck_travel_legs_mode"),
        CheckConstraint("arrives_at >= departs_at", name="ck_travel_legs_arrives_after_departs"),
        Index("ix_travel_legs_trip_departs", "trip_id", "departs_at"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("travel.trips.id", ondelete="CASCADE"), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    origin: Mapped[str] = mapped_column(String(200), nullable=False)
    destination: Mapped[str] = mapped_column(String(200), nullable=False)
    # The city a terminal, station or address is in: nullable, since some ends can't be matched to a city.
    origin_city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("travel.cities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    destination_city_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("travel.cities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    origin_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    destination_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    departs_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrives_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    departs_tz: Mapped[str] = mapped_column(String(64), nullable=False)
    arrives_tz: Mapped[str] = mapped_column(String(64), nullable=False)
    carrier: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    number: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    booking_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    booking_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    seat: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Set when the leg was imported from a calendar event; unique so the same event is imported once.
    calendar_event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizer.calendar_events.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    origin_city: Mapped[Optional[City]] = relationship(City, foreign_keys=[origin_city_id], lazy="joined")
    destination_city: Mapped[Optional[City]] = relationship(City, foreign_keys=[destination_city_id], lazy="joined")
