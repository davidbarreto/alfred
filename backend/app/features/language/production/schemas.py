from typing import Annotated

from fastapi import Query
from pydantic import BaseModel

from app.features.language.sessions.schemas import ProductionTaskType

PRODUCTION_TASK_TYPES: tuple[str, ...] = ("sentence", "translate")
OPEN_ENDED_TASK_TYPES: tuple[str, ...] = ("journal", "timed")
ALL_TASK_TYPES: tuple[str, ...] = PRODUCTION_TASK_TYPES + OPEN_ENDED_TASK_TYPES


class ProductionTaskRead(BaseModel):
    """A production exercise the user should answer next."""
    track_id: int
    track_code: str
    language_name: str
    chunk_id: int | None
    task_type: ProductionTaskType
    prompt_text: str
    text: str | None
    translation: str | None
    total_due: int
    time_limit_seconds: int | None = None


class ProductionAttemptCreate(BaseModel):
    track_id: int
    chunk_id: int | None = None
    task_type: ProductionTaskType
    prompt_text: str
    response_text: str


class NewVocabularyCandidate(BaseModel):
    text: str
    translation: str


class ProductionGradingRead(BaseModel):
    score: float
    errors: list[str]
    corrected_text: str
    feedback: str
    new_vocabulary: list[NewVocabularyCandidate]


class ProductionAttemptRead(BaseModel):
    session_id: int
    track_id: int
    chunk_id: int | None
    task_type: str
    quality_score: float
    grading: ProductionGradingRead


class TrackMasteryStates(BaseModel):
    """Per-SRS-state chunk counts for one modality (recognition or production)."""
    new: int = 0
    learning: int = 0
    review: int = 0
    relearning: int = 0
    due: int = 0


class ProductionMasteryRead(BaseModel):
    track_id: int
    track_code: str
    total_active: int
    recognition: TrackMasteryStates
    production: TrackMasteryStates
    production_locked: int


class NextTaskFilters:
    def __init__(
        self,
        track_id: Annotated[int, Query()],
        task_type: Annotated[ProductionTaskType | None, Query()] = None,
    ) -> None:
        self.track_id = track_id
        self.task_type = task_type
