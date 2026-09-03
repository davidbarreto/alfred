from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.organizer.interviews.stages.tables import InterviewStage


class InterviewProcess(Base):
    __tablename__ = "interview_processes"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("organizer.interview_companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applied_date: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    study_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("cs.study_plans.id", ondelete="SET NULL"), nullable=True
    )

    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    work_regime: Mapped[str | None] = mapped_column(String(20), nullable=True)
    office_days_per_month: Mapped[float | None] = mapped_column(Numeric(4, 1), nullable=True)
    office_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    benefits: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_description_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    company_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    stages: Mapped[list["InterviewStage"]] = relationship(
        "InterviewStage", back_populates="process", order_by="InterviewStage.sequence"
    )
