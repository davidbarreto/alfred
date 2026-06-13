from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional
from datetime import datetime

from app.db.base import Base


class Monitor(Base):
    __tablename__ = "monitors"
    __table_args__ = {"schema": "monitoring"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="html_static")
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    json_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    page_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=32)
    max_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    request_delay: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    wait_selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    executions: Mapped[list["Execution"]] = relationship(
        "Execution",
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = {"schema": "monitoring"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    monitor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitoring.monitors.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # found, not_found, error
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    monitor: Mapped["Monitor"] = relationship("Monitor", back_populates="executions")
    alert: Mapped[Optional["Alert"]] = relationship(
        "Alert", back_populates="execution", uselist=False
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = {"schema": "monitoring"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    execution_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitoring.executions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending, done
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    execution: Mapped["Execution"] = relationship("Execution", back_populates="alert")
