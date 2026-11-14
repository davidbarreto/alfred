from pydantic import BaseModel, field_validator

from app.shared.tags import normalize_tag_name


class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return normalize_tag_name(value)


class TagUpdate(BaseModel):
    name: str | None = None

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str | None) -> str | None:
        return None if value is None else normalize_tag_name(value)


class TagRead(TagBase):
    id: int

    model_config = {"from_attributes": True}
