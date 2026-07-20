from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_DIR))


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


templates.env.filters["timeago"] = _timeago
templates.env.filters["compact_number"] = _compact_number
templates.env.filters["money"] = _money
