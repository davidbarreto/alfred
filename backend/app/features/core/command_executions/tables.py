from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommandExecution(Base):
    __tablename__ = "command_executions"
    __table_args__ = {"schema": "core"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("core.messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    command_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entities: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
