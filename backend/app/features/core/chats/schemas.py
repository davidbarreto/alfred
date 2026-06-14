from typing import Any, Literal

from pydantic import BaseModel

SourceChannel = Literal["telegram", "api", "web"]


class ExecutedCommandResult(BaseModel):
    type: str
    command: str
    arguments: dict[str, Any] = {}
    result: Any = None


class ChatRequest(BaseModel):
    text: str
    session_id: int | None = None
    source: SourceChannel = "telegram"
    executed_commands: list[ExecutedCommandResult] = []


class ChatResponse(BaseModel):
    response: str
