from pydantic import BaseModel


class UrgencyResetRead(BaseModel):
    days: int
    tasks_urgency_reset: int
    tasks_deadline_moved: int
    tasks_snoozed: int
