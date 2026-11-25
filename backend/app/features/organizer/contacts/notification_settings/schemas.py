from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.features.core.settings.metadata import setting
from app.features.organizer.calendar_events.notification_settings.schemas import check_offsets

BirthdayRelationship = Literal["family", "relative", "friend", "other"]

# The constants used before they became settings: the briefing lists birthdays a week ahead, the dashboard a month.
DEFAULT_BIRTHDAY_LOOKAHEAD_DAYS = 7
DEFAULT_BIRTHDAY_DASHBOARD_DAYS = 30


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
    birthday_lookahead_days: int = setting(
        "Birthdays in the briefing", "The morning briefing lists birthdays this many days ahead (family and "
        "relatives at least 30).",
        unit="days", group="Birthdays ahead", default=DEFAULT_BIRTHDAY_LOOKAHEAD_DAYS, ge=0, le=366,
    )
    birthday_dashboard_days: int = setting(
        "Birthdays on the dashboard", "The dashboard's birthday card looks this many days ahead.",
        unit="days", group="Birthdays ahead", default=DEFAULT_BIRTHDAY_DASHBOARD_DAYS, ge=0, le=366,
    )


class ContactBirthdaySettingsUpdate(BaseModel):
    """Partial update of the look-aheads; a field left out, or null, is untouched. Cascades have their own PUT."""

    birthday_lookahead_days: int | None = Field(default=None, ge=0, le=366)
    birthday_dashboard_days: int | None = Field(default=None, ge=0, le=366)


class ContactBirthdayCascadeUpdate(BaseModel):
    offsets: list[str] = Field(min_length=1)

    @field_validator("offsets")
    @classmethod
    def _offsets(cls, value: list[str]) -> list[str]:
        return check_offsets(value)
