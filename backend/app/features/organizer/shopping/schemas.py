from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional, TypeAlias

from fastapi import Query
from pydantic import BaseModel

ShoppingCategory: TypeAlias = Literal[
    "grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other"
]
ShoppingPriority: TypeAlias = Literal["need", "want"]
ShoppingStatus: TypeAlias = Literal["pending", "bought", "skipped"]


# --- Shopping item ---

class ShoppingItemBase(BaseModel):
    name: str
    category: ShoppingCategory = "other"
    priority: ShoppingPriority = "need"
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    store: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class ShoppingItemCreate(ShoppingItemBase):
    pass


class ShoppingItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ShoppingCategory] = None
    priority: Optional[ShoppingPriority] = None
    quantity: Optional[Decimal] = None
    unit: Optional[str] = None
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    store: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[ShoppingStatus] = None


class ShoppingItemRead(ShoppingItemBase):
    id: int
    status: ShoppingStatus
    last_bought_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShoppingItemFilters:
    def __init__(
        self,
        status: Annotated[Literal["pending", "bought", "skipped", "all"], Query()] = "pending",
        category: Annotated[
            Literal["grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other", "all"],
            Query(),
        ] = "all",
        priority: Annotated[Literal["need", "want", "all"], Query()] = "all",
        limit: Annotated[int, Query(ge=1)] = 100,
    ) -> None:
        self.status = status
        self.category = category
        self.priority = priority
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ShoppingItemFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"ShoppingItemFilters(status={self.status!r}, category={self.category!r}, "
            f"priority={self.priority!r}, limit={self.limit})"
        )


# --- Wishlist item ---

class WishlistItemBase(BaseModel):
    name: str
    category: ShoppingCategory = "other"
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None


class WishlistItemCreate(WishlistItemBase):
    pass


class WishlistItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ShoppingCategory] = None
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None


class WishlistItemRead(WishlistItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WishlistItemFilters:
    def __init__(
        self,
        category: Annotated[
            Literal["grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other", "all"],
            Query(),
        ] = "all",
        limit: Annotated[int, Query(ge=1)] = 100,
    ) -> None:
        self.category = category
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WishlistItemFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"WishlistItemFilters(category={self.category!r}, limit={self.limit})"


# --- Recurrence item ---

class RecurrenceItemBase(BaseModel):
    name: str
    category: ShoppingCategory = "other"
    recurrence_days: int


class RecurrenceItemCreate(RecurrenceItemBase):
    pass


class RecurrenceItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[ShoppingCategory] = None
    recurrence_days: Optional[int] = None
    active: Optional[bool] = None


class RecurrenceItemRead(RecurrenceItemBase):
    id: int
    last_added_at: Optional[datetime]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
