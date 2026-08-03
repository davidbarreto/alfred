from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel

Verdict: TypeAlias = Literal[
    "accepted",
    "wrong_answer",
    "time_limit_exceeded",
    "memory_limit_exceeded",
    "runtime_error",
    "compile_error",
    "other",
]
SourceMethod: TypeAlias = Literal["api_sync", "manual_import"]


class SubmissionCreate(BaseModel):
    platform_id: int
    problem_id: int
    external_id: str
    verdict: Verdict
    verdict_raw: str | None = None
    language: str | None = None
    language_raw: str | None = None
    source_method: SourceMethod = "api_sync"
    submitted_at: datetime


class SubmissionRead(BaseModel):
    id: int
    platform_id: int
    problem_id: int
    external_id: str
    verdict: str
    verdict_raw: str | None
    language: str | None
    language_raw: str | None
    source_method: str
    submitted_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SubmissionFilters:
    def __init__(
        self,
        platform_id: Annotated[int | None, Query()] = None,
        problem_id: Annotated[int | None, Query()] = None,
        verdict: Annotated[str | None, Query()] = None,
        language: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.platform_id = platform_id
        self.problem_id = problem_id
        self.verdict = verdict
        self.language = language
        self.limit = limit
        self.offset = offset
