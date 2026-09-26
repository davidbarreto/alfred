from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _normalize_tags(tags: list[str] | None) -> list[str] | None:
    if tags is None:
        return None
    normalized: list[str] = []
    for tag in tags:
        cleaned = tag.strip()
        if cleaned and cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


class InterviewStoryTagRead(BaseModel):
    id: int
    tag: str

    model_config = {"from_attributes": True}


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
        cleaned = _normalize_tags(value) or []
        if any(len(tag) > 100 for tag in cleaned):
            raise ValueError("tags must be at most 100 characters")
        return cleaned


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
        cleaned = _normalize_tags(value)
        if cleaned and any(len(tag) > 100 for tag in cleaned):
            raise ValueError("tags must be at most 100 characters")
        return cleaned


class InterviewStoryRead(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[InterviewStoryTagRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StoryStrengthAssessment(BaseModel):
    story_id: int
    suggested_strength: int = Field(..., ge=1, le=5)
    reasoning: str
