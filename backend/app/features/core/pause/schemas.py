from datetime import datetime

from pydantic import BaseModel


class PauseStateRead(BaseModel):
    paused: bool
    paused_at: datetime | None = None


class PauseResumeRead(BaseModel):
    paused: bool = False
    resumed_at: datetime
    tasks_urgency_reset: int
    tasks_deadline_shifted: int
