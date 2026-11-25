from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.features.travel.constants import WEB_LINK_KINDS, in_clause


class WebLink(Base):
    """A saved URL (official site, tips, video) owned by exactly one trip, place, city or country."""

    __tablename__ = "links"
    __table_args__ = (
        CheckConstraint("num_nonnulls(trip_id, place_id, city_id, country_id) = 1", name="ck_travel_links_one_parent"),
        CheckConstraint(in_clause("kind", WEB_LINK_KINDS), name="ck_travel_links_kind"),
        UniqueConstraint("trip_id", "url", name="uq_travel_links_trip_url"),
        UniqueConstraint("place_id", "url", name="uq_travel_links_place_url"),
        UniqueConstraint("city_id", "url", name="uq_travel_links_city_url"),
        UniqueConstraint("country_id", "url", name="uq_travel_links_country_url"),
        {"schema": "travel"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    trip_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("travel.trips.id", ondelete="CASCADE"), nullable=True, index=True
    )
    place_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("travel.places.id", ondelete="CASCADE"), nullable=True, index=True
    )
    city_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("location.cities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    country_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("location.countries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
