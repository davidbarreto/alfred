from __future__ import annotations

from datetime import date, datetime
from typing import Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel

from app.features.organizer.interviews.stages.schemas import InterviewStageRead, StageType

ProcessStatus: TypeAlias = Literal["active", "offer", "rejected", "withdrawn", "ghosted"]
Priority: TypeAlias = Literal["low", "medium", "high"]
WorkRegime: TypeAlias = Literal["remote", "hybrid", "onsite"]


class InterviewProcessCreate(BaseModel):
    company_id: int
    role_title: str
    status: ProcessStatus = "active"
    source: str | None = None
    applied_date: date | None = None
    priority: Priority | None = None
    department: str | None = None
    notes: str | None = None
    study_plan_id: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    work_regime: WorkRegime | None = None
    office_days_per_month: float | None = None
    office_location: str | None = None
    benefits: str | None = None
    job_description_url: str | None = None
    company_feedback: str | None = None


class InterviewProcessUpdate(BaseModel):
    company_id: int | None = None
    role_title: str | None = None
    status: ProcessStatus | None = None
    source: str | None = None
    applied_date: date | None = None
    priority: Priority | None = None
    department: str | None = None
    notes: str | None = None
    study_plan_id: int | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    work_regime: WorkRegime | None = None
    office_days_per_month: float | None = None
    office_location: str | None = None
    benefits: str | None = None
    job_description_url: str | None = None
    company_feedback: str | None = None


class InterviewProcessRead(BaseModel):
    id: int
    company_id: int
    role_title: str
    status: str
    source: str | None
    applied_date: date | None
    priority: str | None
    department: str | None
    notes: str | None
    study_plan_id: int | None
    salary_min: int | None
    salary_max: int | None
    salary_currency: str | None
    work_regime: str | None
    office_days_per_month: float | None
    office_location: str | None
    benefits: str | None
    job_description_url: str | None
    company_feedback: str | None
    stages: list[InterviewStageRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InterviewProcessFilters:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        company_id: int | None = Query(None),
        status: str | None = Query(None),
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.company_id = company_id
        self.status = status


class FirstStageInput(BaseModel):
    stage_type: StageType
    scheduled_at: datetime | None = None


class InterviewProcessCreateWithFirstStage(BaseModel):
    process: InterviewProcessCreate
    first_stage: FirstStageInput | None = None
