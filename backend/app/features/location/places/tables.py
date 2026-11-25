from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.location.cities.tables import City
from app.features.location.places.constants import HOME_KIND, kind_check


class Place(Base):
    """Any place the user knows: home, the office, the supermarket, a hotel or a museum on a trip.

    What a place is lives here; how it is used lives in the domain that uses it: the everyday role in
    `organizer.everyday_places`, the trip role in travel's visits, stays, tags and links.
    """

    __tablename__ = "places"
    __table_args__ = (
        CheckConstraint(kind_check(), name="ck_places_kind"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_places_coordinates"),
        {"schema": "location"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # One of PLACE_KINDS; "home" is unique, "work" is where office days happen.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    # Every place has a city; forms and commands default it to the Home place's city.
    city_id: Mapped[int] = mapped_column(ForeignKey("location.cities.id", ondelete="RESTRICT"), nullable=False, index=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    maps_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Both or neither; typed on the form or read from the Maps link. The weather is looked up here.
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    # Per weekday plus "hol" (see hours.py); null = unknown every day.
    opening_hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    city: Mapped[City] = relationship(City, lazy="joined")


# Unique name within a city, ignoring case, archived places included.
Index("uq_places_name_city", func.lower(Place.name), Place.city_id, unique=True)
# At most one home.
Index("uq_places_home", Place.kind, unique=True, postgresql_where=Place.kind == HOME_KIND)
