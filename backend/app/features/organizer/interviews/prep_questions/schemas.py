from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.features.organizer.interviews.tags.schemas import InterviewTagRead, normalize_tags


class InterviewStoryForQuestion(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[InterviewTagRead]
    fit_score: int


class InterviewPrepQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        return normalize_tags(value) or []


class InterviewPrepQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = Field(default=None)

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str] | None) -> list[str] | None:
        return normalize_tags(value)


class InterviewPrepQuestionRead(BaseModel):
    id: int
    text: str
    tags: list[InterviewTagRead] = []
    story_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewPrepQuestionWithStories(BaseModel):
    id: int
    text: str
    tags: list[InterviewTagRead]
    stories: list[InterviewStoryForQuestion]
    created_at: datetime
    updated_at: datetime


class StoryLinkCreate(BaseModel):
    fit_score: int = Field(default=3, ge=1, le=5)


class StoryLinkRead(BaseModel):
    question_id: int
    story_id: int
    fit_score: int

    model_config = {"from_attributes": True}
