from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Describe the trip itself (Family, Work). Unrelated to trips.default_tag_names, which holds finance tag names.
trips_tags = Table(
    "trips_tags",
    Base.metadata,
    Column("trip_id", ForeignKey("travel.trips.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("travel.tags.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="travel",
)


# Describe the place itself (Would return, Family friendly).
places_tags = Table(
    "places_tags",
    Base.metadata,
    Column("place_id", ForeignKey("travel.places.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("travel.tags.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="travel",
)


class TravelTag(Base):
    __tablename__ = "tags"
    __table_args__ = {"schema": "travel"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Names are unique ignoring case so "Family" and "family" can't coexist.
Index("uq_travel_tags_name_lower", func.lower(TravelTag.name), unique=True)
