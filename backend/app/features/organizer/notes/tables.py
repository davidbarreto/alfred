from sqlalchemy import Boolean, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import List, Optional, TYPE_CHECKING, Union

from app.features.organizer.tags.tables import Tag
from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.tasks.tables import Task

class Note(Base):
    __tablename__ = "notes"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("organizer.tasks.id"), nullable=True)

    # Relationships
    task: Mapped[Optional["Task"]] = relationship(
        "Task",
        back_populates="notes",
    )
    
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.notes_tags",
        back_populates="notes",
    )
