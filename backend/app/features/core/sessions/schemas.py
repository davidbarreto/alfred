from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    source: Optional[str] = None
    external_id: Optional[str] = None
    summary: Optional[str] = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: Optional[str] = None
    external_id: Optional[str] = None
    summary: Optional[str] = None
    last_interaction_at: datetime
    created_at: datetime
    finished_at: Optional[datetime] = None


class SessionFilters(BaseModel):
    active_only: bool = False
