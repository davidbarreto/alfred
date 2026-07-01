from datetime import datetime
from typing import Annotated, Any, List, Optional
from pydantic import BaseModel, field_validator
from fastapi import Query


class EventBase(BaseModel):
    title: str
    description: str | None = None
    location: str | None = None
    start_datetime: datetime
    end_datetime: datetime
    all_day: bool = False
    host: str | None = None
    invitees: list[str] = []
    tags: list[str] = []
    recurrence_rule: str | None = None


class EventCreate(EventBase):
    pass


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    all_day: bool | None = None
    host: str | None = None
    invitees: list[str] | None = None
    tags: list[str] | None = None
    recurrence_rule: str | None = None


class EventRead(EventBase):
    id: int

    model_config = {"from_attributes": True}

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: Any) -> list[str]:
        return [item.name if hasattr(item, "name") else item for item in v]

    @field_validator("invitees", mode="before")
    @classmethod
    def coerce_invitees(cls, v: Any) -> list[str]:
        return [item.email if hasattr(item, "email") else item for item in v]


class EventFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        start_from: Annotated[Optional[datetime], Query()] = None,
        start_to: Annotated[Optional[datetime], Query()] = None,
        tags: Annotated[Optional[List[str]], Query()] = None,
    ) -> None:
        self.limit = limit
        self.start_from = start_from.replace(tzinfo=None) if start_from is not None else None
        self.start_to = start_to.replace(tzinfo=None) if start_to is not None else None
        self.tags = tags

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EventFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"EventFilters(limit={self.limit}, start_from={self.start_from!r}, "
            f"start_to={self.start_to!r}, tags={self.tags!r})"
        )
