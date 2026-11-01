from datetime import datetime
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import Query
from pydantic import BaseModel, field_validator


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("name must not be blank")
    return cleaned


class ShoppingProductCreate(BaseModel):
    name: str
    category_id: Optional[int] = None
    default_unit: Optional[str] = None
    default_quantity: Optional[Decimal] = None

    _normalize_name = field_validator("name")(_clean_name)


class ShoppingProductUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[int] = None
    default_unit: Optional[str] = None
    default_quantity: Optional[Decimal] = None

    _normalize_name = field_validator("name")(_clean_name)


class ShoppingProductRead(BaseModel):
    id: int
    name: str
    category_id: Optional[int]
    default_unit: Optional[str]
    default_quantity: Optional[Decimal]
    purchase_count: int = 0
    pending: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShoppingProductMerge(BaseModel):
    into_id: int


class ShoppingProductFilters:
    def __init__(
        self,
        q: Annotated[Optional[str], Query()] = None,
        category_id: Annotated[Optional[int], Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.q = q
        self.category_id = category_id
        self.limit = limit
        self.offset = offset

    def __eq__(self, other: object) -> bool:
        return isinstance(other, ShoppingProductFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"ShoppingProductFilters(q={self.q!r}, category_id={self.category_id!r}, "
            f"limit={self.limit}, offset={self.offset})"
        )
