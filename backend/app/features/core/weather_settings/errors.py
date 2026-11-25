class WeatherPlaceNotFoundError(LookupError):
    """The chosen location or city does not exist (404)."""


class WeatherPlaceInvalidError(ValueError):
    """A place the weather cannot use: both a location and a city, or a location without coordinates (422)."""
