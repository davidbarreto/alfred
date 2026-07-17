from sqlalchemy import DateTime, Integer, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.accounts.tables import Account
    from app.features.finance.categories.tables import Category


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="EUR")
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bank_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    merchant: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    counterpart_account_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.accounts.id", ondelete="SET NULL"), nullable=True
    )
    import_batch_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.import_batches.id", ondelete="SET NULL"), nullable=True
    )
    deduplication_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship(
        "Account", back_populates="transactions", foreign_keys=[account_id]
    )
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="transactions")
