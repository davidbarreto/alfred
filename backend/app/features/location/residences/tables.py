from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.location.cities.tables import City


class Residence(Base):
    """A period the user lived in a city (`docs/modules/places.md`, Places lived).

    The dates lived are `from_date` up to, not including, `to_date` (the moving day belongs to the next row). A null
    `from_date` means "since birth" (the birth row only); a null `to_date` means still living there. The Home place
    stays the source of the current home: nothing here follows it on its own.
    """

    __tablename__ = "residences"
    __table_args__ = (
        CheckConstraint("from_date IS NOT NULL OR born", name="ck_location_residences_from_date"),
        CheckConstraint(
            "to_date IS NULL OR from_date IS NULL OR to_date > from_date", name="ck_location_residences_period"
        ),
        {"schema": "location"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("location.cities.id", ondelete="RESTRICT"), nullable=False, index=True)
    from_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    to_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # The birthplace row; at most one.
    born: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    city: Mapped[City] = relationship(City, lazy="joined")


Index("uq_location_residences_born", Residence.born, unique=True, postgresql_where=Residence.born)
# At most one open row (still living there).
Index("uq_location_residences_open", Residence.to_date.is_(None), unique=True, postgresql_where=Residence.to_date.is_(None))
