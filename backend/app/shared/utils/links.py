"""Plain web URLs for maps, photos and flight lookups. No API, key or quota is involved: the browser opens them."""
from urllib.parse import quote, quote_plus, urlencode, urlsplit

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


def photos_search_url(term: str) -> str:
    """The user's own Google Photos library searched by a place name (it indexes photos by where they were taken)."""
    return f"https://photos.google.com/search/{quote(term.strip(), safe='')}"


# Host suffix -> the album button's label; anything else is a "Photo album".
_ALBUM_HOSTS = (
    (("photos.google.com", "photos.app.goo.gl"), "Google Photos"),
    (("icloud.com",), "iCloud"),
    (("flickr.com", "flic.kr"), "Flickr"),
    (("onedrive.live.com", "1drv.ms"), "OneDrive"),
)


def photo_album_label(url: str | None) -> str | None:
    """What a trip's photo album link is, from its domain ("Google Photos", "iCloud", ...); None without a link."""
    if not url:
        return None
    host = (urlsplit(url).hostname or "").lower()
    for suffixes, label in _ALBUM_HOSTS:
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return label
    return "Photo album"
