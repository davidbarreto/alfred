from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.organizer.interviews.tags.tables import InterviewTag, interview_story_tag_links

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

    tags: Mapped[list[InterviewTag]] = relationship(
        InterviewTag, secondary=interview_story_tag_links, order_by=InterviewTag.name
    )
    prep_questions: Mapped[list[InterviewPrepQuestion]] = relationship(
        "InterviewPrepQuestion",
        secondary="organizer.interview_story_questions",
        back_populates="stories",
        viewonly=True,
    )
