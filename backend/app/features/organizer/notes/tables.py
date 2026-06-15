from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import List

from app.features.organizer.tags.tables import Tag
from app.db.base import Base


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_notes_provider_id"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.notes_tags",
        back_populates="notes",
    )
