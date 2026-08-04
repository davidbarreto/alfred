from datetime import date, datetime
from typing import Annotated, Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel

Cadence: TypeAlias = Literal["weekly", "monthly"]
ItemType: TypeAlias = Literal["problem", "topic_review", "resource", "custom"]


class StudyPlanItemCreate(BaseModel):
    item_type: ItemType
    description: str
    problem_id: int | None = None
    url: str | None = None
    position: int = 0


class StudyPlanItemRead(BaseModel):
    id: int
    item_type: str
    description: str
    problem_id: int | None
    url: str | None
    is_done: bool
    completed_at: datetime | None
    position: int

    model_config = {"from_attributes": True}


class StudyPlanCreate(BaseModel):
    cadence: Cadence
    period_start: date
    rationale: str | None = None
    items: list[StudyPlanItemCreate] = []


class StudyPlanRead(BaseModel):
    id: int
    cadence: str
    period_start: date
    status: str
    rationale: str | None
    items: list[StudyPlanItemRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StudyPlanFilters:

    def __init__(
        self,
        cadence: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.cadence = cadence
        self.limit = limit
        self.offset = offset
