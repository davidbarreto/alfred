from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    summary: Optional[str] = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    summary: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class SessionFilters(BaseModel):
    active_only: bool = False
