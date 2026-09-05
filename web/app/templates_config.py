from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import get_settings

_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_DIR))
templates.env.globals["is_dev"] = get_settings().env.lower() not in ("production", "prod")


def _timeago(dt_str: str | None) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        diff = now - dt
        s = int(diff.total_seconds())
        if s < 60:
            return "just now"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        d = s // 86400
        if d < 7:
            return f"{d}d ago"
        return str(dt_str)[:10]
    except Exception:
        return str(dt_str)[:10] if dt_str else ""


def _compact_number(value: int | float | None) -> str:
    if value is None:
        return ""
    n = float(value)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n < 1000:
        return f"{sign}{int(n)}"
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if n >= divisor:
            return f"{sign}{n / divisor:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{sign}{int(n)}"


def _money(value: int | float | None, decimals: int = 2) -> str:
    if value is None:
        return ""
    return f"{float(value):,.{decimals}f}"


_COUNTRY_TO_CODE = {
    "portugal": "PT", "ireland": "IE", "united kingdom": "GB", "uk": "GB", "england": "GB",
    "great britain": "GB", "scotland": "GB", "wales": "GB", "united states": "US", "usa": "US",
    "us": "US", "united states of america": "US", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "the netherlands": "NL", "holland": "NL", "belgium": "BE",
    "switzerland": "CH", "austria": "AT", "poland": "PL", "czech republic": "CZ", "czechia": "CZ",
    "hungary": "HU", "romania": "RO", "bulgaria": "BG", "greece": "GR", "sweden": "SE",
    "norway": "NO", "denmark": "DK", "finland": "FI", "iceland": "IS", "estonia": "EE",
    "latvia": "LV", "lithuania": "LT", "slovakia": "SK", "slovenia": "SI", "croatia": "HR",
    "serbia": "RS", "ukraine": "UA", "russia": "RU", "turkey": "TR", "luxembourg": "LU",
    "malta": "MT", "cyprus": "CY", "canada": "CA", "mexico": "MX", "brazil": "BR",
    "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE", "india": "IN",
    "china": "CN", "japan": "JP", "south korea": "KR", "korea": "KR", "singapore": "SG",
    "indonesia": "ID", "malaysia": "MY", "thailand": "TH", "vietnam": "VN", "philippines": "PH",
    "australia": "AU", "new zealand": "NZ", "south africa": "ZA", "israel": "IL",
    "united arab emirates": "AE", "uae": "AE", "saudi arabia": "SA", "egypt": "EG",
    "morocco": "MA", "nigeria": "NG", "kenya": "KE", "pakistan": "PK", "bangladesh": "BD",
}

_CITY_TO_CODE = {
    "dublin": "IE", "cork": "IE", "london": "GB", "manchester": "GB", "edinburgh": "GB",
    "belfast": "GB", "lisbon": "PT", "porto": "PT", "berlin": "DE", "munich": "DE",
    "hamburg": "DE", "frankfurt": "DE", "cologne": "DE", "paris": "FR", "lyon": "FR",
    "madrid": "ES", "barcelona": "ES", "valencia": "ES", "milan": "IT", "rome": "IT",
    "amsterdam": "NL", "rotterdam": "NL", "eindhoven": "NL", "brussels": "BE",
    "zurich": "CH", "geneva": "CH", "basel": "CH", "vienna": "AT", "warsaw": "PL",
    "krakow": "PL", "wroclaw": "PL", "prague": "CZ", "brno": "CZ", "budapest": "HU",
    "bucharest": "RO", "cluj": "RO", "sofia": "BG", "athens": "GR", "stockholm": "SE",
    "gothenburg": "SE", "oslo": "NO", "copenhagen": "DK", "helsinki": "FI",
    "reykjavik": "IS", "tallinn": "EE", "riga": "LV", "vilnius": "LT", "bratislava": "SK",
    "ljubljana": "SI", "zagreb": "HR", "belgrade": "RS", "kyiv": "UA", "istanbul": "TR",
    "luxembourg city": "LU", "toronto": "CA", "vancouver": "CA", "montreal": "CA",
    "new york": "US", "san francisco": "US", "seattle": "US", "austin": "US",
    "boston": "US", "chicago": "US", "los angeles": "US", "denver": "US",
    "mexico city": "MX", "sao paulo": "BR", "rio de janeiro": "BR", "buenos aires": "AR",
    "bogota": "CO", "bangalore": "IN", "mumbai": "IN", "delhi": "IN", "hyderabad": "IN",
    "shanghai": "CN", "beijing": "CN", "shenzhen": "CN", "tokyo": "JP", "osaka": "JP",
    "seoul": "KR", "jakarta": "ID", "kuala lumpur": "MY", "bangkok": "TH", "hanoi": "VN",
    "manila": "PH", "sydney": "AU", "melbourne": "AU", "auckland": "NZ",
    "cape town": "ZA", "johannesburg": "ZA", "tel aviv": "IL", "dubai": "AE",
    "abu dhabi": "AE", "riyadh": "SA", "cairo": "EG", "casablanca": "MA",
    "lagos": "NG", "nairobi": "KE", "karachi": "PK", "dhaka": "BD",
}


def _flag_emoji_for_code(code: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def _country_flag(location: str | None) -> str:
    if not location:
        return ""
    parts = [p.strip().lower() for p in location.split(",") if p.strip()]
    if not parts:
        return ""
    for part in (parts[-1], parts[0]):
        if part in _COUNTRY_TO_CODE:
            return _flag_emoji_for_code(_COUNTRY_TO_CODE[part])
    for part in parts:
        if part in _CITY_TO_CODE:
            return _flag_emoji_for_code(_CITY_TO_CODE[part])
    return ""


templates.env.filters["timeago"] = _timeago
templates.env.filters["compact_number"] = _compact_number
templates.env.filters["money"] = _money
templates.env.filters["country_flag"] = _country_flag
