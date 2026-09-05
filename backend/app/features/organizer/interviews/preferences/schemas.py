from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class InterviewPreferencesRead(BaseModel):
    id: int
    work_regimes: list[str]
    target_office_days_per_month: float | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    locations: list[str]
    tech_stack: list[str]
    roles: list[str]
    career_objectives: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewPreferencesUpdate(BaseModel):
    work_regimes: list[str] | None = None
    target_office_days_per_month: float | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    locations: list[str] | None = None
    tech_stack: list[str] | None = None
    roles: list[str] | None = None
    career_objectives: str | None = None
