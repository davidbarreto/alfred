from typing import Any, List, NamedTuple, Dict
from pydantic import BaseModel

class CommandMetadata(NamedTuple):
    type: str
    action: str
    flags: Dict[str, str]
    requires_args: bool = False
    arg_keys: List[str] = []
    implicit_flags: Dict[str, Any] = {}

class CommandDetail(BaseModel):
    type: str
    command: str
    confidence: float
    source: str
    arguments: dict[str, Any]

class CommandResolveRequest(BaseModel):
    text: str
    command: str | None = None
    args: str | None = None


class CommandExecuteRequest(BaseModel):
    type: str
    command: str
    arguments: dict[str, Any]


class CommandExecuteResponse(BaseModel):
    type: str
    command: str
    status: str
    result: Any = None

class CommandResolveResponse(BaseModel):
    status: str
    commands: List[CommandDetail]
    raw_text: str
