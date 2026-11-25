from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# What a place sells: the shopping categories the day plan matches pending items against.
places_shopping_categories = Table(
    "places_shopping_categories",
    Base.metadata,
    Column("place_id", Integer, ForeignKey("location.places.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "category_id", Integer, ForeignKey("organizer.shopping_categories.id", ondelete="CASCADE"),
        primary_key=True, index=True,
    ),
    schema="organizer",
)


class EverydayPlace(Base):
    """One of the user's everyday places: on the Everyday list, the day plan, `--sells` and the event *At* picker.

    The Home place is always everyday and needs no row.
    """

    __tablename__ = "everyday_places"
    __table_args__ = {"schema": "organizer"}

    place_id: Mapped[int] = mapped_column(ForeignKey("location.places.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
