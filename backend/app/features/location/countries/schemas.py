from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CountryRef(BaseModel):
    id: int
    name: str
    code: str | None = None

    model_config = {"from_attributes": True}


class CountryRead(CountryRef):
    default_tag_names: str | None = None
    created_at: datetime
    updated_at: datetime


class CountryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # ISO 3166-1 alpha-2; null clears it.
    code: str | None = Field(default=None, min_length=2, max_length=2)
    default_tag_names: str | None = None

    @field_validator("code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.isalpha() or not value.isascii():
            raise ValueError("code must be two letters")
        return value.upper()
