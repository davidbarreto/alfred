from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

SourceChannel = Literal["telegram", "api", "web"]


class MessageCreate(BaseModel):
    session_id: int
    source: SourceChannel
    input: str
    response: Optional[str] = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    source: str
    input: str
    response: Optional[str] = None
    created_at: datetime


class MessageFilters(BaseModel):
    session_id: Optional[int] = None
    source: Optional[str] = None
