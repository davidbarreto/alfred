from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.interviews.stories.tables import InterviewStory


class InterviewPrepQuestion(Base):
    __tablename__ = "interview_prep_questions"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    stories: Mapped[list[InterviewStory]] = relationship(
        "InterviewStory",
        secondary="organizer.interview_story_questions",
        back_populates="prep_questions",
        viewonly=True,
    )
    story_links: Mapped[list[InterviewPrepQuestionStory]] = relationship(
        "InterviewPrepQuestionStory", back_populates="question", cascade="all, delete-orphan"
    )


class InterviewPrepQuestionStory(Base):
    __tablename__ = "interview_story_questions"
    __table_args__ = (
        UniqueConstraint("story_id", "question_id", name="uq_story_question"),
        CheckConstraint("fit_score BETWEEN 1 AND 5", name="ck_interview_story_questions_fit_score"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_prep_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 1-5 how well the story answers this question; scale defined in CLAUDE.md "Interview Prep Module"
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped[InterviewPrepQuestion] = relationship("InterviewPrepQuestion", back_populates="story_links")
    story: Mapped[InterviewStory] = relationship("InterviewStory")
