from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.db.base import Base


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    stored_file: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    closing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class ImportRule(Base):
    __tablename__ = "import_rules"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="auto")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    merchant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True
    )
    transfer_account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
