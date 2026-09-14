from datetime import datetime

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PauseLog(Base):
    __tablename__ = "pause_log"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tasks_urgency_reset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_deadline_shifted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
