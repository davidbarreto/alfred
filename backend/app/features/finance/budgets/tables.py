from sqlalchemy import DateTime, Integer, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.categories.tables import Category


class BudgetTarget(Base):
    __tablename__ = "budget_targets"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.categories.id", ondelete="RESTRICT"), nullable=True
    )
    tag_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.tags.id", ondelete="CASCADE"), nullable=True
    )
    """Exactly one of category_id / tag_id is set (ck_budget_targets_one_subject). A tag
    target takes the budgeted tag's transactions out of their categories' budgets."""
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    effective_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="budget_targets")
