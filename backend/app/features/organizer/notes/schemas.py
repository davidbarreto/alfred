from typing import Annotated, Any, Optional, List
from pydantic import BaseModel, field_validator
from fastapi import Query


class NoteBase(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = []


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class NoteRead(NoteBase):
    id: int

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]


class NoteFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        tags: Annotated[Optional[List[str]], Query()] = None,
    ) -> None:
        self.limit = limit
        self.tags = tags

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NoteFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return f"NoteFilters(limit={self.limit}, tags={self.tags!r})"
