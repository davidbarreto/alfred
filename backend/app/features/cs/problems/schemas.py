from datetime import datetime
from typing import Annotated

from fastapi import Query
from pydantic import BaseModel


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


class ProblemFilters:
    def __init__(
        self,
        platform_id: Annotated[int | None, Query()] = None,
        difficulty: Annotated[str | None, Query()] = None,
        tag: Annotated[str | None, Query()] = None,
    ) -> None:
        self.platform_id = platform_id
        self.difficulty = difficulty
        self.tag = tag
