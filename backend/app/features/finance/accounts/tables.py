from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.transactions.tables import Transaction
    from app.features.finance.recurring_transactions.tables import RecurringTransaction


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    institution: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="account", passive_deletes=True
    )
    recurring_transactions: Mapped[List["RecurringTransaction"]] = relationship(
        "RecurringTransaction", back_populates="account", passive_deletes=True
    )
