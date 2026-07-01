from sqlalchemy import Boolean, Date, Integer, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING
from datetime import date
from decimal import Decimal

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.accounts.tables import Account
    from app.features.finance.categories.tables import Category


class RecurringTransaction(Base):
    __tablename__ = "recurring_transactions"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    merchant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    recurrence_rule: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_occurrence_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    account: Mapped["Account"] = relationship("Account", back_populates="recurring_transactions")
    category: Mapped[Optional["Category"]] = relationship("Category")
