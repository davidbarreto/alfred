from pydantic import BaseModel, Field


class TravelSettingsRead(BaseModel):
    airport_buffer_min: int
    home_to_airport_min: int
    home_address: str | None = None
    max_visits_per_day: int = 4
    visit_duration_min: int = 90
    # During a trip, reminders of calendar events that are not part of it are held back.
    snooze_other_events: bool = False


class TravelSettingsUpdate(BaseModel):
    airport_buffer_min: int | None = Field(default=None, ge=0, le=600)
    home_to_airport_min: int | None = Field(default=None, ge=0, le=600)
    max_visits_per_day: int | None = Field(default=None, ge=1, le=20)
    visit_duration_min: int | None = Field(default=None, ge=5, le=720)
    snooze_other_events: bool | None = None
    # Where trips start; used for the home -> airport directions. An empty string clears it.
    home_address: str | None = Field(default=None, max_length=300)
