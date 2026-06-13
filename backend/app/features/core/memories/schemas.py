from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MemoryCategory = Literal["fact", "preference", "relationship", "skill", "episodic", "goal"]


class MemoryCreate(BaseModel):
    category: MemoryCategory
    content: str
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    active: bool = True
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None
    origin_message_id: Optional[int] = None


class MemoryUpdate(BaseModel):
    content: Optional[str] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    active: Optional[bool] = None
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None


class MemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    content: str
    importance: float
    confidence: float
    active: bool
    expires_at: Optional[datetime] = None
    extra_metadata: Optional[dict[str, Any]] = None
    origin_message_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class MemoryFilters(BaseModel):
    category: Optional[str] = None
    active: Optional[bool] = None
