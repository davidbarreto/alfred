from pydantic import BaseModel, field_validator

from app.features.core.settings.metadata import setting
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
    airport_buffer_min: int | None = setting(
        "At the airport before departure", "With the ride there, gives the leave-home time and its reminder.",
        unit="min", group="Getting to the airport", ge=0, le=600,
    )
    home_to_airport_min: int | None = setting(
        "Ride from home to the airport", "", unit="min", group="Getting to the airport", ge=0, le=600,
    )
    max_visits_per_day: int | None = setting(
        "Visits per day at most", "More than this on one day of a trip is a warning.",
        unit="visits", group="Trip warnings", ge=1, le=20,
    )
    visit_duration_min: int | None = setting(
        "Visit length", "How long a visit's calendar event lasts; two closer than this overlap.",
        unit="min", group="Trip warnings", ge=5, le=720,
    )
    unpaid_leg_days: int | None = setting(
        "Warn about unpaid legs from", "Days before a trip starts. 0 = never.",
        unit="days before", group="Trip warnings", ge=0, le=365,
    )
    snooze_other_events: bool | None = setting(
        "Snooze other events during a trip",
        "Hold back reminders of calendar events that are not part of the trip while it runs.",
        group="Reminders",
    )
    # Moved to the Home location: sending it is refused, so an old client fails loudly instead of being ignored.
    home_address: str | None = setting(
        "Home address", "Where the home → airport directions start. It is the Home location's address.",
        widget="readonly", href="/locations", group="Home",
    )
    # Send null to clear the home city (an unknown id is a 404).
    home_city_id: int | None = setting(
        "Home city", "The city trips start from. Empty = none.",
        widget="city", group="Home",
        confirm_note="Trips that have already started keep the old home city.",
    )

    @field_validator("home_address")
    @classmethod
    def _home_address_moved(cls, value: str | None) -> str | None:
        raise ValueError(
            "home_address moved to the Home location: change it with PATCH /organizer/locations/{id} "
            "(find Home with GET /organizer/locations?kind=home) or on the portal's Locations page"
        )
