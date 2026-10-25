from datetime import date, datetime
from typing import Annotated, Any, List, Literal, Optional
from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator
from fastapi import Query

from app.shared.timezone import local_timezone

NotificationProfile = Literal["cant_miss", "important", "normal", "light", "aware"]
EventAvailability = Literal["blocked", "light", "free"]
EventPresence = Literal["in_person", "remote_home", "remote_anywhere"]


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
    timezone: str | None = None
    notification_profile: NotificationProfile | None = None
    availability: EventAvailability | None = None
    presence: EventPresence = "in_person"
    travel_minutes: int = Field(default=0, ge=0)
    routine_id: int | None = None


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
    timezone: str | None = None
    notification_profile: NotificationProfile | None = None
    availability: EventAvailability | None = None
    presence: EventPresence | None = None
    travel_minutes: int | None = Field(default=None, ge=0)
    routine_id: int | None = None

    @model_validator(mode="after")
    def _required_columns_not_null(self) -> "EventUpdate":
        # presence and travel_minutes are NOT NULL columns: they can be changed, never cleared.
        for field in ("presence", "travel_minutes"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


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

    @field_serializer("start_datetime", "end_datetime", when_used="json")
    def serialize_with_offset(self, value: datetime) -> str:
        # Stored values are naive local time; attaching the zone makes the offset explicit
        # (and DST-correct) for API and MCP consumers. isoformat keeps "+00:00" where
        # pydantic's own datetime encoding would print "Z".
        aware = value.replace(tzinfo=local_timezone()) if value.tzinfo is None else value
        return aware.isoformat()


def _to_local_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(local_timezone()).replace(tzinfo=None)


class EventFilters:
    def __init__(
        self,
        limit: Annotated[int, Query(ge=1)] = 100,
        start_from: Annotated[Optional[datetime], Query()] = None,
        start_to: Annotated[Optional[datetime], Query()] = None,
        tags: Annotated[Optional[List[str]], Query()] = None,
        q: Annotated[Optional[str], Query(description="Case-insensitive substring match on title")] = None,
    ) -> None:
        self.limit = limit
        self.start_from = _to_local_naive(start_from)
        self.start_to = _to_local_naive(start_to)
        self.tags = tags
        self.q = q

    def __eq__(self, other: object) -> bool:
        return isinstance(other, EventFilters) and vars(self) == vars(other)

    def __repr__(self) -> str:
        return (
            f"EventFilters(limit={self.limit}, start_from={self.start_from!r}, "
            f"start_to={self.start_to!r}, tags={self.tags!r}, q={self.q!r})"
        )


class CalendarSyncResult(BaseModel):
    created: int
    updated: int
    start: date
    end: date
