"""Plain web URLs for maps and flight lookups. No API, key or quota is involved: the browser opens them."""
from urllib.parse import quote_plus, urlencode

_MAPS = "https://www.google.com/maps"


def maps_search_url(query: str) -> str:
    return f"{_MAPS}/search/?{urlencode({'api': 1, 'query': query})}"


def maps_directions_url(origin: str, destination: str, mode: str = "transit") -> str:
    return f"{_MAPS}/dir/?{urlencode({'api': 1, 'origin': origin, 'destination': destination, 'travelmode': mode})}"


def place_maps_url(name: str, city: str | None, maps_url: str | None, lat: float | None, lng: float | None) -> str:
    """The user's own link wins, then pasted coordinates, then a name + city search."""
    if maps_url:
        return maps_url
    if lat is not None and lng is not None:
        return maps_search_url(f"{lat},{lng}")
    return maps_search_url(" ".join(part for part in (name, city) if part))


def check_flight_url(carrier: str | None, number: str | None) -> str | None:
    if not carrier or not number:
        return None
    return f"https://www.google.com/search?q={quote_plus(f'flight {carrier} {number}')}"
