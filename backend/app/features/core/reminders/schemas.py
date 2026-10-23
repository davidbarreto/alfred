from datetime import date

from pydantic import BaseModel, Field


class ReminderDigest(BaseModel):
    date: date
    has_content: bool
    text: str


class ReminderSettingsRead(BaseModel):
    overload_overdue_threshold: int
    overload_urgent_threshold: int
    overload_max_listed: int
    overload_urgent_interval_hours: int
    overdue_grace_hours_high: int
    overdue_grace_hours_medium: int
    overdue_grace_hours_low: int
    undated_escalation_days_high: int
    undated_escalation_days_medium: int
    undated_escalation_days_low: int
    urgency_reset_days: int


class ReminderSettingsUpdate(BaseModel):
    overload_overdue_threshold: int | None = Field(default=None, ge=1, le=100)
    overload_urgent_threshold: int | None = Field(default=None, ge=1, le=100)
    overload_max_listed: int | None = Field(default=None, ge=1, le=50)
    overload_urgent_interval_hours: int | None = Field(default=None, ge=1, le=24)
    overdue_grace_hours_high: int | None = Field(default=None, ge=0, le=24 * 90)
    overdue_grace_hours_medium: int | None = Field(default=None, ge=0, le=24 * 90)
    overdue_grace_hours_low: int | None = Field(default=None, ge=0, le=24 * 90)
    undated_escalation_days_high: int | None = Field(default=None, ge=1, le=365)
    undated_escalation_days_medium: int | None = Field(default=None, ge=1, le=365)
    undated_escalation_days_low: int | None = Field(default=None, ge=1, le=365)
    urgency_reset_days: int | None = Field(default=None, ge=1, le=365)
