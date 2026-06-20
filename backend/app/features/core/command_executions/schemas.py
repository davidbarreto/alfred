from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

CommandStatus = Literal["pending", "success", "error"]


class CommandExecutionCreate(BaseModel):
    message_id: int
    command_name: str
    entities: Optional[dict[str, Any]] = None
    status: CommandStatus = "pending"


class CommandExecutionUpdate(BaseModel):
    status: Optional[CommandStatus] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    executed_at: Optional[datetime] = None


class CommandExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int
    command_name: str
    entities: Optional[dict[str, Any]] = None
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    executed_at: Optional[datetime] = None
    created_at: datetime


class CommandExecutionFilters(BaseModel):
    message_id: Optional[int] = None
    status: Optional[str] = None
    command_name: Optional[str] = None
