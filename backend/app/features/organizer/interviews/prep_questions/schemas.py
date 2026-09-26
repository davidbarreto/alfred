from pydantic import BaseModel, Field


class StoryTagRead(BaseModel):
    id: int
    tag: str


class InterviewStoryForQuestion(BaseModel):
    id: int
    situation: str
    task: str
    action: str
    result: str
    strength: int
    tags: list[StoryTagRead]

    # From join table
    priority: int

    model_config = {"from_attributes": True}


class InterviewPrepQuestionCreate(BaseModel):
    text: str = Field(..., min_length=1)


class InterviewPrepQuestionUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1)


class InterviewPrepQuestionRead(BaseModel):
    id: int
    text: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class InterviewPrepQuestionWithStories(BaseModel):
    id: int
    text: str
    stories: list[InterviewStoryForQuestion]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
