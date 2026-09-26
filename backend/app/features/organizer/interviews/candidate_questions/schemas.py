from pydantic import BaseModel, Field


class InterviewCandidateQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)


class InterviewCandidateQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)
    category: str | None = Field(default=None, min_length=1)


class InterviewCandidateQuestionRead(BaseModel):
    id: int
    text: str
    category: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
