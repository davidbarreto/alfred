from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.travel.places.tables import Place


class Stay(Base):
    __tablename__ = "stays"
    __table_args__ = (
        CheckConstraint("check_out_at >= check_in_at", name="ck_travel_stays_out_after_in"),
        CheckConstraint("grade IS NULL OR grade BETWEEN 1 AND 5", name="ck_travel_stays_grade"),
        Index("ix_travel_stays_trip_check_in", "trip_id", "check_in_at"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # A weekend in a hotel needs no trip; deleting a trip keeps its stays (and their notes and grades).
    trip_id: Mapped[Optional[int]] = mapped_column(ForeignKey("travel.trips.id", ondelete="SET NULL"), nullable=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("travel.places.id", ondelete="RESTRICT"), nullable=False, index=True)
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    check_out_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # IANA zone of the lodging, so a check-in time is comparable with a flight's arrival instant.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    booking_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    booking_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    place: Mapped[Place] = relationship(Place, lazy="joined")
