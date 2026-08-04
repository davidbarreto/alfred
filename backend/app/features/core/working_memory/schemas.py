from datetime import datetime
from typing import Annotated, Literal, Optional, TypeAlias

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field

WorkingMemoryExpiredFilter: TypeAlias = Literal["all", "active", "expired"]


class WorkingMemoryCreate(BaseModel):
    key: str
    value: str
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    expires_at: Optional[datetime] = None
    session_id: Optional[int] = None


class WorkingMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
    importance: Optional[float] = None
    expires_at: Optional[datetime] = None
    session_id: Optional[int] = None
    created_at: datetime


class WorkingMemoryFilters:
    def __init__(
        self,
        key: Annotated[Optional[str], Query()] = None,
        key_contains: Annotated[Optional[str], Query()] = None,
        key_prefix: Annotated[Optional[str], Query()] = None,
        session_id: Annotated[Optional[int], Query()] = None,
        expired: Annotated[WorkingMemoryExpiredFilter, Query()] = "all",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.key = key
        self.key_contains = key_contains
        self.key_prefix = key_prefix
        self.session_id = session_id
        self.expired = expired
        self.limit = limit
        self.offset = offset

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WorkingMemoryFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"WorkingMemoryFilters(key={self.key!r}, key_contains={self.key_contains!r}, "
            f"key_prefix={self.key_prefix!r}, session_id={self.session_id!r}, "
            f"expired={self.expired!r}, limit={self.limit}, offset={self.offset})"
        )
