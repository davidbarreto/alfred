from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.location.places.tables import Place


class TravelTime(Base):
    """Door-to-door minutes from one place to another by one mode; two-way unless the reverse is stored too."""

    __tablename__ = "travel_times"
    __table_args__ = (
        CheckConstraint("origin_place_id <> destination_place_id", name="ck_travel_times_distinct"),
        CheckConstraint("minutes BETWEEN 1 AND 600", name="ck_travel_times_minutes"),
        UniqueConstraint("origin_place_id", "destination_place_id", "mode", name="uq_travel_times_route"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # RESTRICT: a place with travel times is not deleted silently (409 listing them; archive it instead).
    origin_place_id: Mapped[int] = mapped_column(
        ForeignKey("location.places.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_place_id: Mapped[int] = mapped_column(
        ForeignKey("location.places.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Free text, lowercase (metro, foot, car, bus...).
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    origin: Mapped[Place] = relationship(Place, foreign_keys=[origin_place_id], lazy="joined")
    destination: Mapped[Place] = relationship(Place, foreign_keys=[destination_place_id], lazy="joined")
