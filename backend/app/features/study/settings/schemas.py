from pydantic import BaseModel, Field


class StudySettingsRead(BaseModel):
    max_active_plans: int


class StudySettingsUpdate(BaseModel):
    max_active_plans: int = Field(ge=1, le=10)
