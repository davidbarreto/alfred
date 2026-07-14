from datetime import datetime
from typing import Annotated, Any, Optional, List
from pydantic import BaseModel, field_validator
from fastapi import Query


class NoteBase(BaseModel):
    title: str
    content: str = ""
    tags: list[str] = []


class NoteCreate(NoteBase):
    pass


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


class NoteRead(NoteBase):
    id: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]


class NoteFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        offset: Annotated[int, Query(ge=0)] = 0,
        tags: Annotated[Optional[List[str]], Query()] = None,
        archived: Annotated[bool, Query()] = False,
        sort: Annotated[str, Query()] = "created",
    ) -> None:
        self.limit = limit
        self.offset = offset
        self.tags = tags
        self.archived = archived
        self.sort = sort

    def __eq__(self, other: object) -> bool:
        return isinstance(other, NoteFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"NoteFilters(limit={self.limit}, offset={self.offset}, tags={self.tags!r}, "
            f"archived={self.archived}, sort={self.sort!r})"
        )
