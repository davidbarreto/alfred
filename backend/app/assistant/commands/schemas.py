from typing import Any, List, NamedTuple, Dict
from pydantic import BaseModel, model_validator

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
    intent: str = ""
    confidence: float
    source: str
    args: dict[str, Any]

    @model_validator(mode="after")
    def _set_intent(self) -> "CommandDetail":
        if not self.intent:
            self.intent = f"{self.type}.{self.command}"
        return self


class CommandDetectRequest(BaseModel):
    text: str
    command: str | None = None
    args: str | None = None


class CommandDetectResponse(BaseModel):
    operation_type: str | None = None
    commands: List[CommandDetail]
    raw_text: str


class CommandExtractRequest(BaseModel):
    text: str
    intent: str


class CommandExtractResponse(BaseModel):
    intent: str
    args: dict[str, Any]


class CommandExecuteRequest(BaseModel):
    message_id: int
    type: str
    command: str
    args: dict[str, Any]


class CommandExecuteResponse(BaseModel):
    command_execution_id: int
    type: str
    command: str
    status: str
    result: Any = None


class CommandRespondRequest(BaseModel):
    message_id: int


class CommandRespondResponse(BaseModel):
    response: str
