from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

plans_tags = Table(
    "plans_tags",
    Base.metadata,
    Column("plan_id", Integer, ForeignKey("study.plans.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("study.tags.id", ondelete="CASCADE"), primary_key=True),
    schema="study",
)


class StudyTag(Base):
    """Free-form label for grouping study plans (e.g. "system-design", "behavioral").

    Named StudyTag (not Tag) to avoid a SQLAlchemy declarative-registry class-name
    collision with organizer.tags.tables.Tag; the table is still "study.tags"."""

    __tablename__ = "tags"
    __table_args__ = {"schema": "study"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
