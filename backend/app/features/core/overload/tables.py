from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OverloadLog(Base):
    """One row per day the reminder run executed: how heavy the task backlog got."""

    __tablename__ = "overload_log"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False)  # worst level reached that day
    last_level: Mapped[str] = mapped_column(String(16), nullable=False)  # level at the latest run
    peak_overdue: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peak_urgent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peak_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reminder_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_listed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_omitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_overloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
