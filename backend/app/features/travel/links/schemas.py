from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.features.travel.constants import WebLinkKind

_MAX_URL = 2000


def _clean_url(value: str) -> str:
    url = value.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("url must be an http or https address")
    if len(url) > _MAX_URL:
        raise ValueError(f"url must be at most {_MAX_URL} characters")
    return url


class WebLinkCreate(BaseModel):
    url: str
    kind: WebLinkKind | None = None
    title: str | None = Field(default=None, max_length=300)
    notes: str | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        return _clean_url(value)


class WebLinkUpdate(BaseModel):
    url: str | None = None
    kind: WebLinkKind | None = None
    title: str | None = Field(default=None, max_length=300)
    notes: str | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, value: str | None) -> str | None:
        return None if value is None else _clean_url(value)


class WebLinkRead(BaseModel):
    id: int
    trip_id: int | None
    place_id: int | None
    url: str
    kind: WebLinkKind
    title: str | None
    description: str | None
    image_url: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
