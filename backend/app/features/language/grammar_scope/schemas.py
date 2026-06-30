from datetime import datetime
from typing import Annotated, Literal, TypeAlias
from fastapi import Query
from pydantic import BaseModel

ScopeStatus: TypeAlias = Literal["active", "deferred", "mastered"]
ScopeStatusFilter: TypeAlias = Literal["active", "deferred", "mastered", "ALL"]


class GrammarScopeCreate(BaseModel):
    track_id: int
    category: str
    value: str
    priority: int = 0
    status: ScopeStatus = "deferred"


class GrammarScopeUpdate(BaseModel):
    category: str | None = None
    value: str | None = None
    priority: int | None = None
    status: ScopeStatus | None = None


class GrammarScopeRead(BaseModel):
    id: int
    track_id: int
    category: str
    value: str
    priority: int
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GrammarScopeFilters:
    def __init__(
        self,
        track_id: Annotated[int | None, Query()] = None,
        status: Annotated[ScopeStatusFilter, Query()] = "ALL",
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.track_id = track_id
        self.status = status
        self.limit = limit
        self.offset = offset
