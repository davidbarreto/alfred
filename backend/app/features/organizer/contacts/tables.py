from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from app.db.base import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("provider_id", name="uq_contacts_provider_id"),
        {"schema": "organizer"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    birthday: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    relationship: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
