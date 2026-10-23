from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.shared.flags import country_flag

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


def _duration(seconds: int | float | None) -> str:
    """Seconds as '45 s', '34 min', '1 h 05 min'; mirrors the backend's /mstop reply."""
    if seconds is None:
        return ""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if rest else f"{hours} h"


def _local_dt(dt_str: str | None) -> str:
    """An ISO timestamp rendered like '21 Oct 08:02' in the portal's configured timezone."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(get_settings().timezone)).strftime("%d %b %H:%M")
    except Exception:
        return str(dt_str)[:16]


def _number(value: int | float | None) -> str:
    """Up to 3 significant decimals, no trailing zeros (7.5, 12, 0.25)."""
    if value is None:
        return ""
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


templates.env.filters["timeago"] = _timeago
templates.env.filters["duration"] = _duration
templates.env.filters["local_dt"] = _local_dt
templates.env.filters["number"] = _number
templates.env.filters["compact_number"] = _compact_number
templates.env.filters["money"] = _money
templates.env.filters["country_flag"] = country_flag
