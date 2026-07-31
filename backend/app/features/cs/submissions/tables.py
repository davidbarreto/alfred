from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.cs.platforms.tables import Platform
    from app.features.cs.problems.tables import Problem


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("platform_id", "external_id", name="uq_cs_submissions_platform_external_id"),
        {"schema": "cs"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    platform_id: Mapped[int] = mapped_column(
        ForeignKey("cs.platforms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    problem_id: Mapped[int] = mapped_column(
        ForeignKey("cs.problems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(50), nullable=False)
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    verdict_raw: Mapped[str | None] = mapped_column(String(50), nullable=True)
    language: Mapped[str | None] = mapped_column(String(30), nullable=True)
    language_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_method: Mapped[str] = mapped_column(String(20), nullable=False, default="api_sync")
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    platform: Mapped["Platform"] = relationship("Platform")
    problem: Mapped["Problem"] = relationship("Problem")
