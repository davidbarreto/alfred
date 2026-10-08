from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.features.organizer.interviews.tags.schemas import InterviewTagRead, normalize_tags


class InterviewStoryCreate(BaseModel):
    situation: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    result: str = Field(..., min_length=1)
    strength: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value) or []


class InterviewStoryUpdate(BaseModel):
    situation: str | None = Field(default=None, min_length=1)
    task: str | None = Field(default=None, min_length=1)
    action: str | None = Field(default=None, min_length=1)
    result: str | None = Field(default=None, min_length=1)
    strength: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = Field(default=None)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return normalize_tags(value)


class InterviewStoryRead(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[InterviewTagRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoryStrengthAssessment(BaseModel):
    story_id: int
    suggested_strength: int = Field(..., ge=1, le=5)
    reasoning: str
