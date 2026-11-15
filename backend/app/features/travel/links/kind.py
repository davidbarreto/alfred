"""Pure helpers on a link's URL: its kind and display domain. No I/O."""
from urllib.parse import urlsplit

_VIDEO_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def display_domain(url: str) -> str:
    return _host(url)


def guess_kind(url: str) -> str:
    """The kind a pasted URL most likely is; the user can override it."""
    host = _host(url)
    path = (urlsplit(url).path or "").lower()
    if _is(host, "instagram.com"):
        return "instagram"
    if _is(host, "tiktok.com"):
        return "tiktok"
    if any(_is(host, domain) for domain in _VIDEO_HOSTS):
        return "video"
    if host == "maps.app.goo.gl" or (_is(host, "google.com") and path.startswith("/maps")):
        return "map"
    return "website"


def is_social(kind: str) -> bool:
    """Instagram and TikTok answer scrapers with a login wall, so a preview is never fetched for them."""
    return kind in ("instagram", "tiktok")
