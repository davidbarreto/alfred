from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

OverloadLevel = Literal["ok", "elevated", "overloaded"]


class OverloadSnapshot(BaseModel):
    level: OverloadLevel
    overdue: int
    urgent: int
    active: int
    overdue_threshold: int
    urgent_threshold: int


class OverloadStatusRead(OverloadSnapshot):
    streak_days: int


class OverloadDayRead(BaseModel):
    date: date
    level: OverloadLevel
    peak_overdue: int
    peak_urgent: int
    peak_active: int
    reminder_runs: int
    tasks_listed: int
    tasks_omitted: int
    first_overloaded_at: datetime | None

    model_config = {"from_attributes": True}
