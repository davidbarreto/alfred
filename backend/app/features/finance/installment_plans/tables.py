from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.db.base import Base


class InstallmentPlan(Base):
    __tablename__ = "installment_plans"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    total_installments: Mapped[int] = mapped_column(Integer, nullable=False)
    plan_ref: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    original_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    """The full, unamortized purchase price -- used to match this plan's original
    lump-sum transaction by (account, description, amount). Null for a manually-created
    plan (e.g. Cetelem/Nubank), which has no lump sum: each month's charge is its own
    real transaction, not a split of one upfront purchase."""
    opened_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    total_interest_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total_duty_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
