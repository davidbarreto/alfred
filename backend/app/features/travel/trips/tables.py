from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.travel.tags.tables import TravelTag, trips_tags


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_travel_trips_dates"),
        Index("ix_travel_trips_start_date", "start_date"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    travelers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preferences: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checklist_note_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizer.notes.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Comma-separated *finance* tag names stamped on transactions dated within the trip.
    default_tag_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[List[TravelTag]] = relationship(
        TravelTag, secondary=trips_tags, lazy="selectin", order_by=TravelTag.name
    )


class TripWeather(Base):
    """The last weather fetched for one day in one city of a trip (a forecast, last year's climate far ahead, or what actually happened for a trip never opened in time)."""
    __tablename__ = "trip_weather"
    __table_args__ = (
        UniqueConstraint("trip_id", "city_key", "day", name="uq_travel_trip_weather_day"),
        CheckConstraint("source IN ('forecast', 'climate', 'actual')", name="ck_travel_trip_weather_source"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("travel.trips.id", ondelete="CASCADE"), nullable=False)
    # Lower-cased city, the key stays and legs are matched on; `city` keeps the spelling to display.
    city_key: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str] = mapped_column(String(200), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    min_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    precip_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # Local calendar date of the fetch: a row fetched today is reused all day, tomorrow's first request refreshes it.
    fetched_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
