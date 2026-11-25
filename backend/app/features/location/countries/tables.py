from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Country(Base):
    __tablename__ = "countries"
    __table_args__ = {"schema": "location"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # ISO 3166-1 alpha-2, uppercase; filled when a form sends the picked city's code or by hand.
    code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    # Comma-separated *finance* tag names; a charge carrying all of them counts towards the country's spend.
    default_tag_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("uq_location_countries_name", func.lower(Country.name), unique=True)
Index("uq_location_countries_code", Country.code, unique=True, postgresql_where=Country.code.is_not(None))
