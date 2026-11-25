from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.location.countries.tables import Country


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_location_cities_coordinates"),
        {"schema": "location"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("location.countries.id", ondelete="RESTRICT"), nullable=False)
    # Comma-separated *finance* tag names; a charge carrying all of them counts towards the city's spend.
    default_tag_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Both or neither; geocoded (Open-Meteo) when the city is created, for its map marker.
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    # The cover photo, relative to MEDIA_STORAGE_DIR, with the credit its licence asks for (`cities/covers.py`).
    cover_path: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cover_credit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cover_source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    country: Mapped[Country] = relationship(Country, lazy="joined")


Index("uq_location_cities_name_country", func.lower(City.name), City.country_id, unique=True)
