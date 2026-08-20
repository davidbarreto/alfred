from pydantic import BaseModel, Field


class CalendarNotificationCascadesRead(BaseModel):
    profiles: dict[str, list[str]]


class CalendarNotificationCascadeUpdate(BaseModel):
    offsets: list[str] = Field(min_length=1)
