from datetime import datetime

from pydantic import BaseModel, Field

from app.features.organizer.interviews.stories.schemas import InterviewStoryTagRead


class InterviewStoryForQuestion(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[InterviewStoryTagRead]
    fit_score: int


class InterviewPrepQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)


class InterviewPrepQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)


class InterviewPrepQuestionRead(BaseModel):
    id: int
    text: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewPrepQuestionWithStories(BaseModel):
    id: int
    text: str
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
