from datetime import datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel

AttemptedStatus = Literal["solved", "unsolved"]


class ProblemCreate(BaseModel):
    platform_id: int
    external_id: str
    name: str
    url: str | None = None
    difficulty_raw: str | None = None
    difficulty: str | None = None
    tags_raw: list[str] | None = None
    tags: list[str] = []


class ProblemUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    difficulty_raw: str | None = None
    difficulty: str | None = None
    tags_raw: list[str] | None = None
    tags: list[str] | None = None


class TagRead(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class ProblemRead(BaseModel):
    id: int
    platform_id: int
    external_id: str
    name: str
    url: str | None
    difficulty_raw: str | None
    difficulty: str | None
    tags_raw: list[str] | None
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AttemptedProblemRead(ProblemRead):
    attempts: int
    solved: bool
    last_attempted_at: datetime


_DEFAULT_PAGE_SIZE = 20


class ProblemFilters:
    def __init__(
        self,
        platform_id: Annotated[int | None, Query()] = None,
        difficulty: Annotated[str | None, Query()] = None,
        tag: Annotated[str | None, Query()] = None,
        q: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = _DEFAULT_PAGE_SIZE,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.platform_id = platform_id
        self.difficulty = difficulty
        self.tag = tag
        self.q = q
        self.limit = limit
        self.offset = offset


class AttemptedProblemFilters:
    def __init__(
        self,
        platform_id: Annotated[int | None, Query()] = None,
        difficulty: Annotated[str | None, Query()] = None,
        tag: Annotated[str | None, Query()] = None,
        status: Annotated[AttemptedStatus | None, Query()] = None,
        q: Annotated[str | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = _DEFAULT_PAGE_SIZE,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> None:
        self.platform_id = platform_id
        self.difficulty = difficulty
        self.tag = tag
        self.status = status
        self.q = q
        self.limit = limit
        self.offset = offset
