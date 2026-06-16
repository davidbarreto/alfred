from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class LlmCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    model: str
    feature: str
    prompt: list[Any]
    response: str
    tokens_input: int | None
    tokens_output: int | None
    latency_ms: int | None
    created_at: datetime
