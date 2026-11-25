from pydantic import BaseModel, Field, field_validator

from app.features.organizer.calendar_events.schemas import NotificationProfile
from app.shared.utils.time_text import parse_offset


def check_offsets(offsets: list[str]) -> list[str]:
    """Each offset must parse ("7d", "4h", "30m", "1mo" or "0"); the bad one is named in the error."""
    for offset in offsets:
        parse_offset(offset)
    return offsets


class CalendarNotificationCascadesRead(BaseModel):
    profiles: dict[NotificationProfile, list[str]] = Field(
        title="Calendar notifications",
        description=(
            "When each notification profile reminds you before an event, as offsets like 7d, 4h, 30m or 0 "
            "(at the start). Events without a profile use normal."
        ),
        json_schema_extra={
            "widget": "json",
            "key": "calendar_notification_cascades",
            "group": "Calendar notifications",
            "write_path": "/organizer/calendar-notification-settings/{entry}",
            "entry_field": "offsets",
        },
    )


class CalendarNotificationCascadeUpdate(BaseModel):
    offsets: list[str] = Field(min_length=1)

    @field_validator("offsets")
    @classmethod
    def _offsets(cls, value: list[str]) -> list[str]:
        return check_offsets(value)
