from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SyncLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider: str
    operation: str
    entity_type: str
    provider_entity_id: str | None
    status: str
    request_payload: dict[str, Any] | None
    response_payload: dict[str, Any] | None
    error: str | None
    created_at: datetime
