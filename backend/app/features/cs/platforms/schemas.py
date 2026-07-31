from datetime import datetime
from typing import Annotated, Literal, TypeAlias

from fastapi import Query
from pydantic import BaseModel

PlatformCode: TypeAlias = Literal["codeforces", "leetcode", "hackerrank", "uva"]


class PlatformCreate(BaseModel):
    code: PlatformCode
    handle: str | None = None
    sync_enabled: bool = True


class PlatformUpdate(BaseModel):
    handle: str | None = None
    sync_enabled: bool | None = None
    last_synced_at: datetime | None = None
    last_submission_external_id: str | None = None
    rating: int | None = None
    max_rating: int | None = None
    rank: str | None = None


class PlatformRead(BaseModel):
    id: int
    code: str
    handle: str | None
    sync_enabled: bool
    last_synced_at: datetime | None
    last_submission_external_id: str | None
    rating: int | None
    max_rating: int | None
    rank: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlatformFilters:
    def __init__(
        self,
        sync_enabled_only: Annotated[bool, Query()] = False,
    ) -> None:
        self.sync_enabled_only = sync_enabled_only
