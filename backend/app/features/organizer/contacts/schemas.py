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
    is_self: bool | None = None


class ContactRead(BaseModel):
    id: int
    provider_id: str
    name: str
    email: str | None
    phone: str | None
    birthday: date | None
    is_self: bool

    model_config = {"from_attributes": True}


class ContactFilters:
    def __init__(
        self,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        name: str | None = Query(None, description="Case-insensitive substring match on name"),
        email: str | None = Query(None, description="Case-insensitive substring match on email"),
        letter: str | None = Query(None, max_length=1, description="Filter by first letter of name"),
        has_birthday: bool | None = Query(None, description="Filter to contacts with (true) or without (false) a birthday"),
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.name = name
        self.email = email
        self.letter = letter.upper() if isinstance(letter, str) and letter else None
        self.has_birthday = has_birthday
