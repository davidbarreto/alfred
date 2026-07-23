from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional, TypeAlias

from fastapi import Query
from pydantic import BaseModel

ShoppingPriority: TypeAlias = Literal["need", "want"]
ShoppingStatus: TypeAlias = Literal["pending", "bought", "skipped"]


# --- Shopping item ---

class ShoppingItemBase(BaseModel):
    name: str
    category_id: Optional[int] = None
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
    category_id: Optional[int] = None
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
    category_id: int
    status: ShoppingStatus
    last_bought_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShoppingItemFilters:
    def __init__(
        self,
        status: Annotated[Literal["pending", "bought", "skipped", "all"], Query()] = "pending",
        category_id: Annotated[Optional[int], Query()] = None,
        priority: Annotated[Literal["need", "want", "all"], Query()] = "all",
        limit: Annotated[int, Query(ge=1)] = 100,
    ) -> None:
        self.status = status
        self.category_id = category_id
        self.priority = priority
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ShoppingItemFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"ShoppingItemFilters(status={self.status!r}, category_id={self.category_id!r}, "
            f"priority={self.priority!r}, limit={self.limit})"
        )


# --- Frequent item (derived from purchase history) ---

class FrequentItemRead(BaseModel):
    name: str
    category_id: int
    purchase_count: int
    last_bought_at: Optional[datetime]


class FrequentItemFilters:
    def __init__(
        self,
        category_id: Annotated[Optional[int], Query()] = None,
        limit: Annotated[int, Query(ge=1)] = 20,
    ) -> None:
        self.category_id = category_id
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FrequentItemFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"FrequentItemFilters(category_id={self.category_id!r}, limit={self.limit})"


# --- Name suggestion (typeahead across shopping/wishlist/recurrence names) ---

class ShoppingNameSuggestion(BaseModel):
    name: str
    category_id: int


class ShoppingNameSuggestionFilters:
    def __init__(
        self,
        q: Annotated[str, Query(min_length=1)],
        limit: Annotated[int, Query(ge=1, le=20)] = 8,
    ) -> None:
        self.q = q
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ShoppingNameSuggestionFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"ShoppingNameSuggestionFilters(q={self.q!r}, limit={self.limit})"


# --- Wishlist item ---

class WishlistItemBase(BaseModel):
    name: str
    category_id: Optional[int] = None
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None


class WishlistItemCreate(WishlistItemBase):
    pass


class WishlistItemUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    estimated_price: Optional[Decimal] = None
    brand: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None


class WishlistItemRead(WishlistItemBase):
    id: int
    category_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WishlistItemFilters:
    def __init__(
        self,
        category_id: Annotated[Optional[int], Query()] = None,
        limit: Annotated[int, Query(ge=1)] = 100,
    ) -> None:
        self.category_id = category_id
        self.limit = limit

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WishlistItemFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"WishlistItemFilters(category_id={self.category_id!r}, limit={self.limit})"


# --- Recurrence item ---

class RecurrenceItemBase(BaseModel):
    name: str
    category_id: Optional[int] = None
    recurrence_days: int


class RecurrenceItemCreate(RecurrenceItemBase):
    pass


class RecurrenceItemUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    recurrence_days: Optional[int] = None
    active: Optional[bool] = None


class RecurrenceItemRead(RecurrenceItemBase):
    id: int
    category_id: int
    last_added_at: Optional[datetime]
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
