from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ShoppingProduct(Base):
    """One row per thing the user buys; shopping_items are the list entries / purchases of it."""

    __tablename__ = "shopping_products"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable so a soft-delete can clear it, releasing the RESTRICT FK (same reason as the
    # old shopping_items.category_id): otherwise a category could never be deleted once any
    # product, even a deleted one, had referenced it.
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizer.shopping_categories.id", ondelete="RESTRICT"), nullable=True
    )
    default_unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    default_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Case-insensitive unique name among live products; a deleted product frees its name.
Index(
    "uq_shopping_products_name",
    func.lower(ShoppingProduct.name),
    unique=True,
    postgresql_where=ShoppingProduct.deleted_at.is_(None),
)
