from __future__ import annotations

from datetime import datetime
from typing import Annotated

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
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.limit = limit
        self.offset = offset
