from datetime import datetime

from pydantic import BaseModel


class StudyTrackRead(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
