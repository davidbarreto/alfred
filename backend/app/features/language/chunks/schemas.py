from datetime import datetime
from typing import Annotated, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel, field_validator

ChunkType: TypeAlias = Literal["word", "collocation", "verb_form", "sentence_pattern"]
ChunkStatus: TypeAlias = Literal["pending_triage", "active", "suspended"]
ChunkStatusFilter: TypeAlias = Literal["pending_triage", "active", "suspended", "ALL"]
FrequencySource: TypeAlias = Literal["pareto_list", "mistake", "llm_suggested", "reading"]
SrsState: TypeAlias = Literal["new", "learning", "review", "relearning"]


class ChunkCreate(BaseModel):
    track_id: int
    grammar_scope_id: int | None = None
    chunk_type: ChunkType
    text: str
    translation: str
    example_sentence: str | None = None
    example_translation: str | None = None
    cefr_level: str | None = None
    frequency_rank: int | None = None
    frequency_source: FrequencySource | None = None
    status: ChunkStatus = "pending_triage"


class ChunkUpdate(BaseModel):
    chunk_type: ChunkType | None = None
    text: str | None = None
    translation: str | None = None
    example_sentence: str | None = None
    example_translation: str | None = None
    cefr_level: str | None = None
    frequency_rank: int | None = None
    frequency_source: FrequencySource | None = None
    status: ChunkStatus | None = None


class ChunkRead(BaseModel):
    id: int
    track_id: int
    grammar_scope_id: int | None
    chunk_type: str
    text: str
    translation: str
    example_sentence: str | None
    example_translation: str | None
    cefr_level: str | None
    frequency_rank: int | None
    frequency_source: str | None
    stability: float
    difficulty: float
    due_at: datetime
    last_review_at: datetime | None
    repetitions: int
    lapses: int
    consecutive_failures: int
    state: str
    status: str
    is_leech: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChunkFilters:
    def __init__(
        self,
        track_id: Annotated[int | None, Query()] = None,
        status: Annotated[ChunkStatusFilter, Query()] = "ALL",
        chunk_type: Annotated[ChunkType | None, Query()] = None,
        is_leech: Annotated[bool | None, Query()] = None,
        due_only: Annotated[bool, Query()] = False,
        cefr_level: Annotated[str | None, Query()] = None,
        difficulty_min: Annotated[float | None, Query(ge=0.0, le=10.0)] = None,
        difficulty_max: Annotated[float | None, Query(ge=0.0, le=10.0)] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.track_id = track_id
        self.status = status
        self.chunk_type = chunk_type
        self.is_leech = is_leech
        self.due_only = due_only
        self.cefr_level = cefr_level
        self.difficulty_min = difficulty_min
        self.difficulty_max = difficulty_max
        self.limit = limit
        self.offset = offset


class ChunkCountRead(BaseModel):
    count: int


class DailyBatchRead(BaseModel):
    track_id: int
    track_code: str
    chunks: list[ChunkRead]
    total_due: int
