from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Many-to-many link tables: one shared tag vocabulary, attached to stories and prep questions.
interview_story_tag_links = Table(
    "interview_story_tag_links",
    Base.metadata,
    Column("story_id", ForeignKey("organizer.interview_stories.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("organizer.interview_tags.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="organizer",
)

interview_question_tag_links = Table(
    "interview_question_tag_links",
    Base.metadata,
    Column("question_id", ForeignKey("organizer.interview_prep_questions.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("organizer.interview_tags.id", ondelete="CASCADE"), primary_key=True, index=True),
    schema="organizer",
)


class InterviewTag(Base):
    __tablename__ = "interview_tags"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# Names are unique ignoring case so "Ownership" and "ownership" can't coexist.
Index("uq_interview_tags_name_lower", func.lower(InterviewTag.name), unique=True)
