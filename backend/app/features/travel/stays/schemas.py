from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.features.travel.places.schemas import PlaceRead
from app.features.travel.zones import to_local, to_utc, validate_zone


class _StayFields(BaseModel):
    booking_ref: str | None = Field(default=None, max_length=64)
    booking_url: str | None = None
    notes: str | None = None
    grade: int | None = Field(default=None, ge=1, le=5)


class StayCreate(_StayFields):
    """check_in_at / check_out_at may be naive (wall time at the lodging) or carry an offset."""

    trip_id: int | None = None
    place_id: int
    check_in_at: datetime
    check_out_at: datetime
    timezone: str
    calendar_event_id: int | None = None

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str) -> str:
        return validate_zone(value)

    @model_validator(mode="after")
    def _to_utc_and_order(self) -> "StayCreate":
        self.check_in_at = to_utc(self.check_in_at, self.timezone)
        self.check_out_at = to_utc(self.check_out_at, self.timezone)
        if self.check_out_at < self.check_in_at:
            raise ValueError("check_out_at cannot be before check_in_at")
        return self


class StayUpdate(_StayFields):
    trip_id: int | None = None
    place_id: int | None = None
    check_in_at: datetime | None = None
    check_out_at: datetime | None = None
    timezone: str | None = None

    @field_validator("timezone")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        return None if value is None else validate_zone(value)


class StayRead(BaseModel):
    id: int
    trip_id: int | None
    place_id: int
    place: PlaceRead
    check_in_at: datetime
    check_out_at: datetime
    timezone: str
    booking_ref: str | None
    booking_url: str | None
    notes: str | None
    grade: int | None
    calendar_event_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def check_in_local(self) -> datetime:
        return to_local(self.check_in_at, self.timezone)

    @computed_field
    @property
    def check_out_local(self) -> datetime:
        return to_local(self.check_out_at, self.timezone)

    @computed_field
    @property
    def nights(self) -> int:
        return max((self.check_out_local.date() - self.check_in_local.date()).days, 0)
