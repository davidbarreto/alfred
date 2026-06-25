from datetime import datetime
from typing import Annotated, Literal, TypeAlias
from fastapi import Query
from pydantic import BaseModel

CefrLevel: TypeAlias = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
ReviewMode: TypeAlias = Literal["balanced", "shadowing_heavy", "recall_heavy"]


class TrackCreate(BaseModel):
    code: str
    name: str
    level: CefrLevel = "A1"
    daily_quota: int = 10
    review_mode: ReviewMode = "balanced"
    active: bool = True


class TrackUpdate(BaseModel):
    name: str | None = None
    level: CefrLevel | None = None
    daily_quota: int | None = None
    review_mode: ReviewMode | None = None
    active: bool | None = None


class TrackRead(BaseModel):
    id: int
    code: str
    name: str
    level: str
    daily_quota: int
    review_mode: str
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrackFilters:
    def __init__(
        self,
        active_only: Annotated[bool, Query()] = True,
    ) -> None:
        self.active_only = active_only
