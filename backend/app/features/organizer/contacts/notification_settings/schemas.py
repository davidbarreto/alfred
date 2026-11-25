from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.features.core.settings.metadata import setting
from app.features.organizer.calendar_events.notification_settings.schemas import check_offsets

BirthdayRelationship = Literal["family", "relative", "friend", "other"]


class ContactBirthdayCascadesRead(BaseModel):
    relationships: dict[BirthdayRelationship, list[str]] = setting(
        "Birthday notifications",
        "When you are reminded before a contact's birthday, per relationship, as offsets like 1mo, 15d or 1d. "
        "Contacts without a relationship use other.",
        widget="json",
        group="Birthday notifications",
        key="contact_birthday_cascades",
        write_path="/organizer/contact-birthday-settings/{entry}",
        entry_field="offsets",
        default=...,
    )


class ContactBirthdayCascadeUpdate(BaseModel):
    offsets: list[str] = Field(min_length=1)

    @field_validator("offsets")
    @classmethod
    def _offsets(cls, value: list[str]) -> list[str]:
        return check_offsets(value)
