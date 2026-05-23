from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func, Float
from sqlalchemy.orm import relationship

from app.db.base import Base

class Monitor(Base):
    __tablename__ = "monitors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    type = Column(String(50), nullable=False, default="html_static")
    url = Column(String(255), nullable=False)
    selector = Column(String(255), nullable=True)
    json_path = Column(String(255), nullable=True)
    target = Column(String(255), nullable=False)
    case_sensitive = Column(Boolean, nullable=False, default=True)
    timeout = Column(Integer, nullable=False, default=10)
    page_size = Column(Integer, nullable=True, default=32)
    max_pages = Column(Integer, nullable=True)
    request_delay = Column(Integer, nullable=True, default=0)
    wait_selector = Column(String(255), nullable=True)

    logs = relationship(
        "MonitorLog",
        back_populates="monitor",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MonitorLog(Base):
    __tablename__ = "monitor_logs"

    id = Column(Integer, primary_key=True, index=True)
    monitor_id = Column(Integer, ForeignKey("monitors.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    monitor_name = Column(String(255), nullable=True)
    monitor_description = Column(Text, nullable=True)
    monitor_type = Column(String(50), nullable=False)
    url = Column(String(255), nullable=False)
    selector = Column(String(255), nullable=True)
    json_path = Column(String(255), nullable=True)
    target = Column(String(255), nullable=False)
    case_sensitive = Column(Boolean, nullable=False, default=True)
    timeout = Column(Integer, nullable=False, default=10)
    page_size = Column(Integer, nullable=True)
    max_pages = Column(Integer, nullable=True)
    request_delay = Column(Integer, nullable=True)
    wait_selector = Column(String(255), nullable=True)
    found = Column(Boolean, nullable=False, default=False)
    elements_checked = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)

    monitor = relationship("Monitor", back_populates="logs")