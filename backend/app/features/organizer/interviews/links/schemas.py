from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InterviewLinkCreate(BaseModel):
    process_id: int
    url: str
    label: str | None = None


class InterviewLinkRead(BaseModel):
    id: int
    process_id: int
    url: str
    label: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
