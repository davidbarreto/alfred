from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional, List
from datetime import datetime

from app.features.organizer.tags.tables import Tag
from app.db.base import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_tasks_provider_id"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(255), nullable=False)
    urgency: Mapped[str] = mapped_column(String(255), nullable=False)
    deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    recurrence_rule: Mapped[str] = mapped_column(String(255), nullable=True)

    tags: Mapped[List["Tag"]] = relationship(
        "Tag",
        secondary="organizer.tasks_tags",
        back_populates="tasks",
    )
