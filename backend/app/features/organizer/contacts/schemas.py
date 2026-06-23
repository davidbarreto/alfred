from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ContactRead(BaseModel):
    id: int
    provider_id: str
    name: str
    email: str | None
    phone: str | None
    birthday: date | None

    model_config = {"from_attributes": True}
