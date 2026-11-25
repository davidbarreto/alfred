from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator

from app.shared.utils.links import photos_search_url


class CountryRef(BaseModel):
    id: int
    name: str
    code: str | None = None

    model_config = {"from_attributes": True}


class CoverFields(BaseModel):
    """A city's or country's cover photo: whether there is one (served by `GET .../cover`) and its credit."""

    cover_path: str | None = Field(default=None, exclude=True)
    cover_credit: str | None = None
    cover_source_url: str | None = None

    @computed_field
    @property
    def has_cover(self) -> bool:
        return self.cover_path is not None


class CountryRead(CoverFields, CountryRef):
    default_tag_names: str | None = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def photos_url(self) -> str:
        """The user's Google Photos library searched by the country's name."""
        return photos_search_url(self.name)


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
