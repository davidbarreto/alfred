from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship, Mapped, mapped_column
from typing import Optional
from datetime import datetime

from app.db.base import Base

class Monitor(Base):
    __tablename__ = "monitors"

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

    logs: Mapped[list["MonitorLog"]] = relationship(
        "MonitorLog",
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MonitorLog(Base):
    __tablename__ = "monitor_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    monitor_id: Mapped[int] = mapped_column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    monitor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    monitor_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monitor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(255), nullable=False)
    selector: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    json_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    page_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    request_delay: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wait_selector = Column(String(255), nullable=True)
    found = Column(Boolean, nullable=False, default=False)
    elements_checked = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)

    monitor = relationship("Monitor", back_populates="logs")