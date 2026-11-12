from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.features.travel.constants import LegMode
from app.features.travel.links import check_flight_url
from app.features.travel.zones import to_local, to_utc, validate_zone


class _LegFields(BaseModel):
    """Optional fields shared by create and update."""

    origin_code: str | None = Field(default=None, max_length=8)
    destination_code: str | None = Field(default=None, max_length=8)
    carrier: str | None = Field(default=None, max_length=100)
    number: str | None = Field(default=None, max_length=32)
    booking_ref: str | None = Field(default=None, max_length=64)
    booking_url: str | None = None
    seat: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class LegCreate(_LegFields):
    """departs_at / arrives_at may be naive (wall time in the matching zone) or carry an offset."""

    trip_id: int
    calendar_event_id: int | None = None
    mode: LegMode
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    departs_at: datetime
    arrives_at: datetime
    departs_tz: str
    arrives_tz: str

    @field_validator("departs_tz", "arrives_tz")
    @classmethod
    def _zone(cls, value: str) -> str:
        return validate_zone(value)

    @model_validator(mode="after")
    def _to_utc_and_order(self) -> "LegCreate":
        self.departs_at = to_utc(self.departs_at, self.departs_tz)
        self.arrives_at = to_utc(self.arrives_at, self.arrives_tz)
        if self.arrives_at < self.departs_at:
            raise ValueError("arrives_at cannot be before departs_at")
        return self


class LegUpdate(_LegFields):
    """Naive times are read in the zone sent with them, else in the leg's stored zone."""

    # Link an existing calendar event, or send null to unlink (the event itself is kept).
    calendar_event_id: int | None = None
    mode: LegMode | None = None
    origin: str | None = Field(default=None, min_length=1, max_length=200)
    destination: str | None = Field(default=None, min_length=1, max_length=200)
    departs_at: datetime | None = None
    arrives_at: datetime | None = None
    departs_tz: str | None = None
    arrives_tz: str | None = None

    @field_validator("departs_tz", "arrives_tz")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        return None if value is None else validate_zone(value)


class LegRead(BaseModel):
    id: int
    trip_id: int
    mode: LegMode
    origin: str
    destination: str
    origin_code: str | None
    destination_code: str | None
    departs_at: datetime
    arrives_at: datetime
    departs_tz: str
    arrives_tz: str
    carrier: str | None
    number: str | None
    booking_ref: str | None
    booking_url: str | None
    seat: str | None
    notes: str | None
    calendar_event_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def departs_local(self) -> datetime:
        return to_local(self.departs_at, self.departs_tz)

    @computed_field
    @property
    def arrives_local(self) -> datetime:
        return to_local(self.arrives_at, self.arrives_tz)

    @computed_field
    @property
    def check_flight_url(self) -> str | None:
        return check_flight_url(self.carrier, self.number) if self.mode == "flight" else None
