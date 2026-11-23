from pydantic import BaseModel, Field, field_validator

from app.features.travel.cities.schemas import CityRef


class TravelSettingsRead(BaseModel):
    airport_buffer_min: int
    home_to_airport_min: int
    home_address: str | None = None
    # The city trips start from; trips started before it changes keep the old one (see the trips' own home columns).
    home_city_id: int | None = None
    home_city: CityRef | None = None
    max_visits_per_day: int = 4
    visit_duration_min: int = 90
    # Warn about legs with no linked charge when the trip starts within this many days (0 = never).
    unpaid_leg_days: int = 30
    # During a trip, reminders of calendar events that are not part of it are held back.
    snooze_other_events: bool = False


class TravelSettingsUpdate(BaseModel):
    airport_buffer_min: int | None = Field(default=None, ge=0, le=600)
    home_to_airport_min: int | None = Field(default=None, ge=0, le=600)
    max_visits_per_day: int | None = Field(default=None, ge=1, le=20)
    visit_duration_min: int | None = Field(default=None, ge=5, le=720)
    unpaid_leg_days: int | None = Field(default=None, ge=0, le=365)
    snooze_other_events: bool | None = None
    # Moved to the Home location: sending it is refused, so an old client fails loudly instead of being ignored.
    home_address: str | None = None
    # Send null to clear the home city (an unknown id is a 404).
    home_city_id: int | None = None

    @field_validator("home_address")
    @classmethod
    def _home_address_moved(cls, value: str | None) -> str | None:
        raise ValueError(
            "home_address moved to the Home location: change it with PATCH /organizer/locations/{id} "
            "(find Home with GET /organizer/locations?kind=home) or on the portal's Locations page"
        )
