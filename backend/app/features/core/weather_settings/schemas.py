from typing import Literal

from pydantic import BaseModel, model_validator

from app.features.core.settings.metadata import setting

WeatherPlaceSource = Literal["location", "city", "home"]

NO_PLACE_HINT = "Add coordinates to the Home location or pick a weather place in Settings."


class WeatherPlace(BaseModel):
    """Where the weather is looked up, resolved from the setting."""

    source: WeatherPlaceSource
    label: str
    latitude: float
    longitude: float


class WeatherChoice(BaseModel):
    id: int
    label: str


class WeatherChoices(BaseModel):
    """What the place picker offers: active locations with coordinates, and the saved cities."""

    locations: list[WeatherChoice]
    cities: list[WeatherChoice]


class WeatherSettingsRead(BaseModel):
    location_id: int | None = None
    city_id: int | None = None
    # What the weather uses now, without asking Open-Meteo: "Home", a location's name, a city, or None.
    place_label: str | None = None
    choices: WeatherChoices


class WeatherSettingsUpdate(BaseModel):
    """At most one of the two; both null (or left out) means the Home location."""

    location_id: int | None = setting(
        "Weather place",
        "Where the briefing, the dashboard and the weather command look up the weather. A location needs "
        "coordinates; a city is found by name. Empty = the Home location.",
        widget="place",
        covers=["city_id"],
    )
    city_id: int | None = setting("Weather city", "Set through the weather place.", widget="hidden")

    @model_validator(mode="after")
    def _one_place(self) -> "WeatherSettingsUpdate":
        if self.location_id is not None and self.city_id is not None:
            raise ValueError("pick a location or a city, not both")
        return self
