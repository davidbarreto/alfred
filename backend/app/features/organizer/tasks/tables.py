from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from app.features.organizer.tags.tables import Tag
from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.notes.tables import Note

class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(255), nullable=False)
    urgency: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    recurrence_rule: Mapped[str] = mapped_column(String(255), nullable=True)

    # Relationships
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    
    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.tasks_tags",
        back_populates="tasks",
    )
