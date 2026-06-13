from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

CommandStatus = Literal["pending", "success", "failure"]


class CommandExecutionCreate(BaseModel):
    message_id: int
    intent: Optional[str] = None
    command_name: Optional[str] = None
    entities: Optional[dict[str, Any]] = None
    status: CommandStatus = "pending"
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class CommandExecutionUpdate(BaseModel):
    status: Optional[CommandStatus] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class CommandExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    intent: Optional[str] = None
    command_name: Optional[str] = None
    entities: Optional[dict[str, Any]] = None
    status: str
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    created_at: datetime


class CommandExecutionFilters(BaseModel):
    message_id: Optional[int] = None
    status: Optional[str] = None
    command_name: Optional[str] = None
