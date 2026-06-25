from __future__ import annotations

from datetime import date

from fastapi import Query
from pydantic import BaseModel


class ContactCreate(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    birthday: date | None = None


class ContactUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    birthday: date | None = None


class ContactRead(BaseModel):
    id: int
    provider_id: str
    name: str
    email: str | None
    phone: str | None
    birthday: date | None

    model_config = {"from_attributes": True}


class ContactFilters:
    def __init__(
        self,
        limit: int = Query(100, ge=1, le=1000),
        name: str | None = Query(None, description="Case-insensitive substring match on name"),
        email: str | None = Query(None, description="Case-insensitive substring match on email"),
        has_birthday: bool | None = Query(None, description="Filter to contacts with (true) or without (false) a birthday"),
    ) -> None:
        self.limit = limit
        self.name = name
        self.email = email
        self.has_birthday = has_birthday
