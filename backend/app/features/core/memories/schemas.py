from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

MemoryCategory = Literal["fact", "preference", "relationship", "skill", "episodic", "goal"]


class MemoryCreate(BaseModel):
    category: MemoryCategory
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    active: bool = True
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None
    origin_message_id: Optional[int] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    content: str
    importance: float
    confidence: float
    active: bool
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None
    origin_message_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


MemorySort = Literal["created_at", "importance"]


class MemoryFilters:
    def __init__(
        self,
        category: Annotated[Optional[str], Query()] = None,
        active: Annotated[Optional[bool], Query()] = None,
        q: Annotated[Optional[str], Query()] = None,
        sort: Annotated[MemorySort, Query()] = "created_at",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.category = category
        self.active = active
        self.q = q
        self.sort = sort
        self.limit = limit
        self.offset = offset

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MemoryFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"MemoryFilters(category={self.category!r}, active={self.active!r}, "
            f"q={self.q!r}, sort={self.sort!r}, limit={self.limit}, offset={self.offset})"
        )
