from datetime import date, datetime, time
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.travel.constants import VISIT_STATUSES, in_clause
from app.features.travel.places.tables import Place
from app.features.travel.trips.tables import Trip


class Visit(Base):
    __tablename__ = "visits"
    __table_args__ = (
        CheckConstraint(in_clause("status", VISIT_STATUSES), name="ck_travel_visits_status"),
        CheckConstraint("grade IS NULL OR grade BETWEEN 1 AND 5", name="ck_travel_visits_grade"),
        Index("ix_travel_visits_trip_date", "trip_id", "visit_date"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("travel.places.id", ondelete="RESTRICT"), nullable=False, index=True)
    # No trip = a restaurant in the home city; a planned visit with no trip is the wishlist.
    trip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("travel.trips.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="planned")
    visit_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # Real for a reservation, approximate if you only want an order within the day.
    visit_time: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    place: Mapped[Place] = relationship(Place, lazy="joined")
    trip: Mapped[Optional[Trip]] = relationship(Trip, lazy="joined")

    @property
    def trip_name(self) -> str | None:
        return self.trip.name if self.trip else None
