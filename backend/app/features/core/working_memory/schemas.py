from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkingMemoryCreate(BaseModel):
    key: str
    value: str
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    expires_at: Optional[datetime] = None
    session_id: Optional[int] = None


class WorkingMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str
    importance: Optional[float] = None
    expires_at: Optional[datetime] = None
    session_id: Optional[int] = None
    created_at: datetime


class WorkingMemoryFilters(BaseModel):
    key: Optional[str] = None
    session_id: Optional[int] = None
    active_only: bool = True
