from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.interviews.prep_questions.tables import InterviewPrepQuestion


class InterviewStory(Base):
    __tablename__ = "interview_stories"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    situation: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    # strength: 1-5 self-assessment of story quality
    # 1=Vague/incomplete, 2=Basic, 3=Good, 4=Strong, 5=Excellent
    # See CLAUDE.md "Interview Prep Module" for full scale definition
    strength: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    tags: Mapped[list[InterviewStoryTag]] = relationship(
        "InterviewStoryTag", back_populates="story", cascade="all, delete-orphan"
    )
    prep_questions: Mapped[list[InterviewPrepQuestion]] = relationship(
        "InterviewPrepQuestion",
        secondary="organizer.interview_story_questions",
        back_populates="stories",
        viewonly=True,
    )


class InterviewStoryTag(Base):
    __tablename__ = "interview_story_tags"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    story: Mapped[InterviewStory] = relationship("InterviewStory", back_populates="tags")
