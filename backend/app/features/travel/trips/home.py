"""Where a trip starts from: the trip's own value when it has one, else the current travel setting. No DB or IO."""
from dataclasses import dataclass

from app.features.travel.settings_schemas import TravelSettingsRead

# The settings a trip keeps its own copy of (columns of `travel.trips`, fields of `TravelSettingsRead`).
HOME_FIELDS = ("home_city_id", "home_address", "airport_buffer_min", "home_to_airport_min")


@dataclass(frozen=True)
class EffectiveHome:
    city_id: int | None
    address: str | None
    airport_buffer_min: int
    home_to_airport_min: int
    # The trip has at least one value of its own.
    from_trip: bool


def effective_home(trip, settings: TravelSettingsRead) -> EffectiveHome:
    """Each value comes from the trip's column when it is not NULL, else from the settings."""
    own = {field: getattr(trip, field) for field in HOME_FIELDS}
    return EffectiveHome(
        city_id=own["home_city_id"] if own["home_city_id"] is not None else settings.home_city_id,
        address=own["home_address"] if own["home_address"] is not None else settings.home_address,
        airport_buffer_min=own["airport_buffer_min"] if own["airport_buffer_min"] is not None else settings.airport_buffer_min,
        home_to_airport_min=(
            own["home_to_airport_min"] if own["home_to_airport_min"] is not None else settings.home_to_airport_min
        ),
        from_trip=any(value is not None for value in own.values()),
    )
