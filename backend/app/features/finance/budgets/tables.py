from sqlalchemy import DateTime, Integer, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional, TYPE_CHECKING
from datetime import datetime
from decimal import Decimal

from app.db.base import Base

if TYPE_CHECKING:
    from app.features.finance.categories.tables import Category


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = {"schema": "finance"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="budgets")
