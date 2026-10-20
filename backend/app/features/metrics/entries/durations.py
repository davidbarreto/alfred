"""Pure helpers for parsing and formatting durations (no DB or IO)."""
import re

_AGO_RE = re.compile(r"^(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$", re.IGNORECASE)


def parse_ago(value: str) -> int:
    """Parse '5m', '1h30m', '90s' or a bare number of minutes into seconds. Raises ValueError."""
    text = value.strip().replace(" ", "")
    if text.isdigit():
        return int(text) * 60
    match = _AGO_RE.match(text)
    if not text or match is None or not any(match.groups()):
        raise ValueError(f"invalid duration {value!r}; use e.g. 5m, 1h30m, 90s")
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} s"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h {rest:02d} min" if rest else f"{hours} h"
