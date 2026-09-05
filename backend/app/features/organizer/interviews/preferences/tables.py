from __future__ import annotations

import datetime

from sqlalchemy import Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime

from app.db.base import Base


class InterviewPreferences(Base):
    __tablename__ = "interview_preferences"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    work_regimes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    target_office_days_per_month: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    locations: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    career_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
