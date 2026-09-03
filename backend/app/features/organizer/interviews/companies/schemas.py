from __future__ import annotations

from fastapi import Query
from pydantic import BaseModel


class CompanyCreate(BaseModel):
    name: str
    website: str | None = None
    notes: str | None = None


class CompanyUpdate(BaseModel):
    name: str | None = None
    website: str | None = None
    notes: str | None = None


class CompanyRead(BaseModel):
    id: int
    name: str
    website: str | None
    notes: str | None

    model_config = {"from_attributes": True}


class CompanyFilters:
    def __init__(
        self,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        name: str | None = Query(None, description="Case-insensitive substring match on name"),
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.name = name
