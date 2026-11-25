"""Coordinates of a location: typed as "41.1579, -8.6291" (what Google Maps copies) or read from a Maps link.

Pure functions; bad input raises ValueError with a message fit to show the user.
"""
import re

_NUMBER = r"(-?\d{1,3}(?:\.\d+)?)"
_TYPED = re.compile(rf"^\s*{_NUMBER}\s*[,;\s]\s*{_NUMBER}\s*$")
# The place's own pin ("!3d41.1579!4d-8.6291") wins over the map's centre ("@41.15,-8.62,17z").
_URL_PATTERNS = (
    re.compile(rf"!3d{_NUMBER}!4d{_NUMBER}"),
    re.compile(rf"[?&](?:q|query|ll)={_NUMBER},\s*{_NUMBER}"),
    re.compile(rf"@{_NUMBER},{_NUMBER}"),
)


def _checked(lat: float, lon: float) -> tuple[float, float]:
    if not -90 <= lat <= 90:
        raise ValueError(f"latitude must be between -90 and 90, got {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"longitude must be between -180 and 180, got {lon}")
    return round(lat, 6), round(lon, 6)


def parse_coordinates(text: str) -> tuple[float, float]:
    """ "41.1579, -8.6291" -> (41.1579, -8.6291): latitude first, as Google Maps copies them."""
    match = _TYPED.match(text)
    if match is None:
        raise ValueError(f"expected coordinates like 41.1579, -8.6291, got {text!r}")
    return _checked(float(match.group(1)), float(match.group(2)))


def coordinates_from_maps_url(url: str | None) -> tuple[float, float] | None:
    """The coordinates a Google Maps link carries, or None (a short maps.app.goo.gl link carries none)."""
    for pattern in _URL_PATTERNS:
        match = pattern.search(url or "")
        if match is not None:
            try:
                return _checked(float(match.group(1)), float(match.group(2)))
            except ValueError:
                return None
    return None
