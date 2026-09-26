from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
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
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    story_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_stories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_prep_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # priority renamed to fit_score: 1-5 assessment of how well the story answers this question
    # 1=Poor fit, 2=Weak fit, 3=Good fit, 4=Strong fit, 5=Excellent fit
    # Stories sorted by fit_score (descending) for each question
    # See CLAUDE.md "Interview Prep Module" for full scale definition
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    question: Mapped[InterviewPrepQuestion] = relationship("InterviewPrepQuestion", back_populates="story_links")
