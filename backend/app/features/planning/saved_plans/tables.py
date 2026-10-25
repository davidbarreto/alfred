from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DayPlan(Base):
    __tablename__ = "day_plans"
    __table_args__ = (
        UniqueConstraint("plan_date", "version", name="uq_day_plans_date_version"),
        CheckConstraint("source IN ('mcp', 'portal')", name="ck_day_plans_source"),
        CheckConstraint("version >= 1", name="ck_day_plans_version"),
        Index(
            "uq_day_plans_active_date",
            "plan_date",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        {"schema": "planning"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan_date: Mapped[date] = mapped_column(Date, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
