from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion


class InterviewStory(Base):
    __tablename__ = "interview_stories"
    __table_args__ = (
        CheckConstraint("strength BETWEEN 1 AND 5", name="ck_interview_stories_strength"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    # 1-5 story quality; scale defined in CLAUDE.md "Interview Prep Module"
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[list[InterviewStoryTag]] = relationship(
        "InterviewStoryTag", back_populates="story", cascade="all, delete-orphan", order_by="InterviewStoryTag.tag"
    )
    prep_questions: Mapped[list[InterviewPrepQuestion]] = relationship(
        "InterviewPrepQuestion",
        secondary="organizer.interview_story_questions",
        back_populates="stories",
        viewonly=True,
    )


class InterviewStoryTag(Base):
    __tablename__ = "interview_story_tags"
    __table_args__ = (
        UniqueConstraint("story_id", "tag", name="uq_story_tag"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    story: Mapped[InterviewStory] = relationship("InterviewStory", back_populates="tags")
