from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Track(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        UniqueConstraint("code", name="uq_language_tracks_code"),
        {"schema": "language"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(5), nullable=False, default="A1")
    daily_quota: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    new_cards_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    review_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="balanced")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    active_tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
