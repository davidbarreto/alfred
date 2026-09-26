from datetime import datetime

from pydantic import BaseModel, Field


class InterviewCandidateQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=50)


class InterviewCandidateQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=500)
    category: str | None = Field(default=None, min_length=1, max_length=50)


class InterviewCandidateQuestionRead(BaseModel):
    id: int
    text: str
    category: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
