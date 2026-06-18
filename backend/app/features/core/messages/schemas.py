from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

MessageRole = Literal["user", "assistant"]
SourceChannel = Literal["telegram", "api", "web"]


class MessageCreate(BaseModel):
    session_id: int
    role: MessageRole
    content: str
    meta: Optional[dict[str, Any]] = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: str
    content: str
    meta: Optional[dict[str, Any]] = None
    created_at: datetime


class MessageFilters(BaseModel):
    session_id: Optional[int] = None
    role: Optional[str] = None
    limit: Optional[int] = None


class MessageIngestRequest(BaseModel):
    text: str
    source: SourceChannel
    external_id: str
    meta: Optional[dict[str, Any]] = None


class MessageIngestResponse(BaseModel):
    message_id: int
    session_id: int
