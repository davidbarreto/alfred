from __future__ import annotations

from datetime import datetime

from fastapi import Query
from pydantic import BaseModel


class InsightsResult(BaseModel):
    content: str
    focus_process_ids: list[int] = []


class InterviewInsightRead(BaseModel):
    id: int
    content: str
    model: str
    process_ids: list[int]
    generated_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewInsightFilters:
    def __init__(
        self,
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ) -> None:
        self.limit = limit
        self.offset = offset
