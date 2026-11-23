from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.organizer.shopping_categories.tables import ShoppingCategory

HOME_KIND = "home"

# What a location sells: the shopping categories the day plan matches pending items against.
locations_shopping_categories = Table(
    "locations_shopping_categories",
    Base.metadata,
    Column("location_id", Integer, ForeignKey("organizer.locations.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "category_id", Integer, ForeignKey("organizer.shopping_categories.id", ondelete="CASCADE"), primary_key=True
    ),
    schema="organizer",
)


class Location(Base):
    """A frequent everyday place: home, the office, school, the supermarket near school."""

    __tablename__ = "locations"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Free text, trimmed and lowercase; only "home" has a meaning in code.
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    maps_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Per weekday plus "hol" (see hours.py); null = unknown every day.
    opening_hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    categories: Mapped[List[ShoppingCategory]] = relationship(
        ShoppingCategory, secondary=locations_shopping_categories, order_by=ShoppingCategory.name
    )


# Case-insensitive unique name, archived rows included.
Index("uq_locations_name", func.lower(Location.name), unique=True)
# At most one home.
Index("uq_locations_home", Location.kind, unique=True, postgresql_where=Location.kind == HOME_KIND)
