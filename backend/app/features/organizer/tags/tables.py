from sqlalchemy import Integer, String, ForeignKey, Table, Column, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import List, TYPE_CHECKING
from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.tasks.tables import Task
    from app.features.organizer.notes.tables import Note


# Association table for Task-Tag relationship
tasks_tags = Table(
    "tasks_tags",
    Base.metadata,
    Column("task_id", Integer, ForeignKey("organizer.tasks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="organizer",
)

# Association table for Note-Tag relationship
notes_tags = Table(
    "notes_tags",
    Base.metadata,
    Column("note_id", Integer, ForeignKey("organizer.notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="organizer",
)


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("provider_id", "name", name="uq_provider_tag_name"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Relationships
    tasks: Mapped[List["Task"]] = relationship(
        "Task",
        secondary=tasks_tags,
        back_populates="tags",
    )
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        secondary=notes_tags,
        back_populates="tags",
    )
