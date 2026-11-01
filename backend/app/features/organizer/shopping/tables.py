from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.features.organizer.shopping_products.tables import ShoppingProduct


class ShoppingItem(Base):
    """A list entry for a product; bought entries stay as purchase history."""

    __tablename__ = "shopping_items"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizer.shopping_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product: Mapped[ShoppingProduct] = relationship(ShoppingProduct, lazy="joined", innerjoin=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default="need")
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    estimated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    store: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_bought_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @property
    def name(self) -> str:
        return self.product.name

    @property
    def category_id(self) -> Optional[int]:
        return self.product.category_id


# At most one live pending entry per product.
Index(
    "uq_shopping_items_pending_product",
    ShoppingItem.product_id,
    unique=True,
    postgresql_where=(ShoppingItem.status == "pending") & ShoppingItem.deleted_at.is_(None),
)


class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable so a soft-delete (see delete()) can clear it, releasing the RESTRICT FK —
    # otherwise a category could never be deleted once any item, even a deleted one,
    # had ever referenced it.
    category_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("organizer.shopping_categories.id", ondelete="RESTRICT"), nullable=True
    )
    estimated_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class RecurrenceItem(Base):
    __tablename__ = "recurrence_items"
    __table_args__ = {"schema": "organizer"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizer.shopping_categories.id", ondelete="RESTRICT"), nullable=False
    )
    recurrence_days: Mapped[int] = mapped_column(Integer, nullable=False)
    last_added_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
