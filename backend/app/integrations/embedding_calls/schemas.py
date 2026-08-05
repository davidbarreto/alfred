from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EmbeddingCallRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature: str
    query_text: str
    source_types: list[str] | None
    top_k: int
    threshold: float
    results: list[dict[str, Any]]
    result_count: int
    latency_ms: int | None
    created_at: datetime
