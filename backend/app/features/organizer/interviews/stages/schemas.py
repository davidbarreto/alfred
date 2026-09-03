from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel

StageType: TypeAlias = Literal[
    "phone_screen", "code_review", "live_coding", "onsite", "behavioral", "system_design", "offer", "other"
]
StageStatus: TypeAlias = Literal["scheduled", "completed", "passed", "failed", "cancelled"]


class InterviewStageCreate(BaseModel):
    process_id: int
    stage_type: StageType
    scheduled_at: datetime | None = None
    status: StageStatus = "scheduled"
    feedback: str | None = None
    notes: str | None = None
    sequence: int = 0
    calendar_event_id: int | None = None


class InterviewStageUpdate(BaseModel):
    stage_type: StageType | None = None
    scheduled_at: datetime | None = None
    status: StageStatus | None = None
    feedback: str | None = None
    notes: str | None = None
    sequence: int | None = None
    calendar_event_id: int | None = None


class InterviewStageRead(BaseModel):
    id: int
    process_id: int
    stage_type: str
    scheduled_at: datetime | None
    status: str
    feedback: str | None
    notes: str | None
    sequence: int
    calendar_event_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewStageFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        process_id: Annotated[int | None, Query()] = None,
        status: Annotated[str | None, Query()] = None,
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.process_id = process_id
        self.status = status


class StageContactLink(BaseModel):
    role: str | None = None
