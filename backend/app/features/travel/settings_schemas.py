from pydantic import BaseModel, ValidationInfo, field_validator

from app.features.core.settings.metadata import setting
from app.features.location.cities.schemas import CityRef

# Each one is a travel.* setting with this default (the constant the code used before).
DEFAULT_LEAVE_HOME_LEAD_MIN = 60
DEFAULT_CHECK_IN_OPENS_HOURS = 24
DEFAULT_CHECKLIST_NUDGE_DAYS = 60
DEFAULT_TIGHT_CONNECTION_MIN = 90
DEFAULT_LONG_WAIT_HOURS = 4
DEFAULT_RAIN_MM = 2.0
DEFAULT_CHARGE_LINK_LEAD_DAYS = 90
DEFAULT_CHARGE_LINK_TAIL_DAYS = 30


class TravelSettingsRead(BaseModel):
    airport_buffer_min: int
    home_to_airport_min: int
    # Where trips start: the Home place's address and city (location.places), never stored here. Trips that have
    # started keep the values they were planned with (the trips' own home columns, written by keep_old_home).
    home_address: str | None = None
    home_city_id: int | None = None
    home_city: CityRef | None = None
    # "<address>, <city>" for the read-only Home row of /settings, and the Home place it links to.
    home: str | None = None
    home_place_id: int | None = None
    max_visits_per_day: int = 4
    visit_duration_min: int = 90
    # Warn about legs with no linked charge when the trip starts within this many days (0 = never).
    unpaid_leg_days: int = 30
    # During a trip, reminders of calendar events that are not part of it are held back.
    snooze_other_events: bool = False
    leave_home_lead_min: int = DEFAULT_LEAVE_HOME_LEAD_MIN
    check_in_opens_hours: int = DEFAULT_CHECK_IN_OPENS_HOURS
    checklist_nudge_days: int = DEFAULT_CHECKLIST_NUDGE_DAYS
    tight_connection_min: int = DEFAULT_TIGHT_CONNECTION_MIN
    long_wait_hours: int = DEFAULT_LONG_WAIT_HOURS
    rain_mm: float = DEFAULT_RAIN_MM
    charge_link_lead_days: int = DEFAULT_CHARGE_LINK_LEAD_DAYS
    charge_link_tail_days: int = DEFAULT_CHARGE_LINK_TAIL_DAYS


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
    leave_home_lead_min: int | None = setting(
        "Time to leave reminder", "How long before the leave-home time it is sent.",
        unit="min before", group="Getting to the airport", ge=0, le=600,
    )
    check_in_opens_hours: int | None = setting(
        "Online check-in opens", "Before a flight; the check-in reminder is sent from then.",
        unit="hours before", group="Getting to the airport", ge=1, le=168,
    )
    tight_connection_min: int | None = setting(
        "Tight connection under", "A connection shorter than this is a warning.",
        unit="min", group="Trip warnings", ge=0, le=600,
    )
    long_wait_hours: int | None = setting(
        "Long wait before check-in over", "Arriving this long before a stay's check-in is a warning.",
        unit="hours", group="Trip warnings", ge=0, le=24,
    )
    checklist_nudge_days: int | None = setting(
        "Checklist reminder from", "Days before a trip, a checklist not generated yet is a warning.",
        unit="days before", group="Trip warnings", ge=0, le=365,
    )
    snooze_other_events: bool | None = setting(
        "Snooze other events during a trip",
        "Hold back reminders of calendar events that are not part of the trip while it runs.",
        group="Reminders",
    )
    rain_mm: float | None = setting(
        "Rain day from", "A trip day with at least this much precipitation counts as rainy.",
        unit="mm", group="Weather", step=0.1, ge=0, le=100,
    )
    charge_link_lead_days: int | None = setting(
        "Tagged charges from", "Charges with the trip's tags count from this long before the trip (prepaid bookings).",
        unit="days before", group="Charges", ge=0, le=730,
    )
    charge_link_tail_days: int | None = setting(
        "Tagged charges until", "…and until this long after it.",
        unit="days after", group="Charges", ge=0, le=365,
    )
    # Read-only: the Home place's address and city. Sending it (or the two fields it replaced) is refused, so an old
    # client fails loudly instead of being ignored.
    home: str | None = setting(
        "Home", "Where trips start and the home → airport directions begin: the Home place's address and city.",
        widget="readonly", href="/locations/home", group="Home",
    )
    home_address: str | None = None
    home_city_id: int | None = None

    @field_validator("home", "home_address", "home_city_id", mode="before")
    @classmethod
    def _home_moved(cls, value: object, info: ValidationInfo) -> object:
        raise ValueError(
            f"{info.field_name} moved to the Home place: change its address or city with PATCH /location/places/{{id}} "
            "(find Home with GET /location/places?kind=home) or on the portal's Locations page"
        )
