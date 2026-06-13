from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EmbeddingCreate(BaseModel):
    source_type: str
    source_id: int
    content: str


class EmbeddingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: int
    content: str
    model: str
    dimensions: int
    embedded_at: datetime


class EmbeddingSearchRequest(BaseModel):
    query: str
    source_types: Optional[list[str]] = None
    limit: int = Field(default=10, ge=1, le=100)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)


class EmbeddingSearchResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str
    source_id: int
    content: str
    model: str
    dimensions: int
    embedded_at: datetime
    similarity: float
