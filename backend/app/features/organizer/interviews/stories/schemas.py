from pydantic import BaseModel, Field


class InterviewStoryTagRead(BaseModel):
    id: int
    tag: str


class InterviewStoryCreate(BaseModel):
    situation: str = Field(..., min_length=1)
    task: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    result: str = Field(..., min_length=1)
    strength: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)


class InterviewStoryUpdate(BaseModel):
    situation: str | None = Field(default=None, min_length=1)
    task: str | None = Field(default=None, min_length=1)
    action: str | None = Field(default=None, min_length=1)
    result: str | None = Field(default=None, min_length=1)
    strength: int | None = Field(default=None, ge=1, le=5)
    tags: list[str] | None = Field(default=None)


class InterviewStoryRead(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[InterviewStoryTagRead]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
