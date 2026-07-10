from datetime import datetime
from typing import Annotated, Any, Literal, Optional, TypeAlias
from fastapi import Query
from pydantic import BaseModel

SessionType: TypeAlias = Literal["srs_review", "shadowing", "production", "conversation", "correction"]
ProductionTaskType: TypeAlias = Literal["sentence", "translate"]
_SRS_FEEDING_TYPES = {"srs_review", "shadowing"}


class SessionCreate(BaseModel):
    track_id: int
    chunk_id: int | None = None
    session_type: SessionType
    audio_ref: str | None = None
    ai_feedback_json: dict[str, Any] | None = None
    quality_score: float | None = None
    transcript_or_notes: str | None = None

    @property
    def feeds_srs(self) -> bool:
        return self.session_type in _SRS_FEEDING_TYPES


class SrsReviewCreate(BaseModel):
    """Convenience body for typed-recall SRS review."""
    track_id: int
    chunk_id: int
    quality_score: float
    transcript_or_notes: str | None = None


class ShadowingSessionCreate(BaseModel):
    """Convenience body for shadowing sessions (audio handled separately)."""
    track_id: int
    chunk_id: int | None = None
    quality_score: float | None = None
    ai_feedback_json: dict[str, Any] | None = None
    transcript_or_notes: str | None = None


class ProductionSessionCreate(BaseModel):
    """Convenience body for production attempts (graded externally by ProductionService)."""
    track_id: int
    chunk_id: int
    task_type: ProductionTaskType
    prompt_text: str
    quality_score: float | None = None
    ai_feedback_json: dict[str, Any] | None = None
    transcript_or_notes: str | None = None


class SessionRead(BaseModel):
    id: int
    track_id: int
    chunk_id: int | None
    session_type: str
    task_type: str | None
    prompt_text: str | None
    feeds_srs: bool
    audio_ref: str | None
    ai_feedback_json: dict[str, Any] | None
    quality_score: float | None
    transcript_or_notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionFilters:
    def __init__(
        self,
        track_id: Annotated[int | None, Query()] = None,
        chunk_id: Annotated[int | None, Query()] = None,
        session_type: Annotated[SessionType | None, Query()] = None,
        task_type: Annotated[ProductionTaskType | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.track_id = track_id
        self.chunk_id = chunk_id
        self.session_type = session_type
        self.task_type = task_type
        self.limit = limit
        self.offset = offset


class DailyProgressRead(BaseModel):
    track_id: int
    track_code: str
    daily_quota: int
    completed_today: int
    quota_met: bool


class NextPracticePrompt(BaseModel):
    """The next rep in an active practice/review loop, returned after a chat reply so the
    caller (n8n) can prompt the user again without a separate lookup."""
    mode: Literal["practice", "review"]
    track_id: int
    track_code: str
    chunk_id: int
    text: str
    translation: str | None
    language_name: str
    remaining: int
