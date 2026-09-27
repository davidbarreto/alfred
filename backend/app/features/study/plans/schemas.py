from datetime import datetime
from typing import Annotated, Any, Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel, Field, field_validator

PlanStatus: TypeAlias = Literal["backlog", "active", "completed", "abandoned"]
PlanPriority: TypeAlias = Literal["low", "medium", "high"]
ItemSourceType: TypeAlias = Literal["cs_tag", "interview_stage", "interview_process", "story_gap", "manual"]


class StudyPlanItemCreate(BaseModel):
    description: str = Field(min_length=1)
    url: str | None = None
    position: int = 0
    source_type: ItemSourceType = "manual"
    source_id: int | None = None
    reason: str | None = None


class StudyPlanItemRead(BaseModel):
    id: int
    description: str
    url: str | None
    is_done: bool
    position: int
    source_type: str
    source_id: int | None
    reason: str | None

    model_config = {"from_attributes": True}


class StudyPlanCreate(BaseModel):
    track_id: int
    title: str = Field(min_length=1, max_length=255)
    goal: str = Field(min_length=1)
    priority: PlanPriority = "medium"
    tags: list[str] = []
    items: list[StudyPlanItemCreate] = []


class StudyPlanRead(BaseModel):
    id: int
    track_id: int
    title: str
    goal: str
    priority: str
    status: str
    activated_at: datetime | None
    completed_at: datetime | None
    tags: list[str]
    items: list[StudyPlanItemRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]


class StudyPlansOverview(BaseModel):
    active: list[StudyPlanRead]
    backlog: list[StudyPlanRead]
    max_active_plans: int


class StudyPlanFilters:

    def __init__(
        self,
        status: Annotated[PlanStatus | None, Query()] = None,
        closed: Annotated[bool | None, Query(description="true = completed or abandoned only")] = None,
        track_id: Annotated[int | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.status = status
        self.closed = closed
        self.track_id = track_id
        self.limit = limit
        self.offset = offset
