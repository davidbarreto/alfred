import re
from datetime import datetime, date
from typing import Optional
import dateparser

from app.nlp.patterns import _CLEANUP_RE, PRIORITY_MAP

def normalize_date(raw: str, base_date: Optional[datetime] = None) -> Optional[str]:
    """Parse any date string to ISO 8601 date (YYYY-MM-DD)."""
    if not raw:
        return None

    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    if base_date:
        if isinstance(base_date, datetime):
            settings["RELATIVE_BASE"] = base_date
        else:
            settings["RELATIVE_BASE"] = datetime(
                base_date.year,
                base_date.month,
                base_date.day,
                0,
                0,
                0,
            )

    parsed = dateparser.parse(raw, settings=settings)
    if parsed:
        return parsed.strftime("%Y-%m-%d")

    # Fallback manual parsing for relative keywords (useful when dateparser
    # cannot parse phrases like 'next monday' without an explicit base).
    try:
        from datetime import timedelta

        # determine base for relative calculations
        if base_date is None:
            base = datetime.now().date()
        elif hasattr(base_date, "date"):
            base = base_date.date()
        else:
            base = base_date

        clean = raw.lower().strip()
        # keywords
        if clean == "today":
            return base.isoformat()
        if clean == "tomorrow":
            return (base + timedelta(days=1)).isoformat()
        if clean == "yesterday":
            return (base - timedelta(days=1)).isoformat()

        # ISO
        if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
            return clean

        weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        # handle 'next monday' / 'this tuesday' forms
        m_next = re.match(r"^(next|this)\s+(%s)$" % "|".join(weekdays), clean)
        if m_next:
            prefix = m_next.group(1)
            wd = m_next.group(2)
            target_idx = weekdays.index(wd)
            current_idx = base.weekday()
            days_ahead = target_idx - current_idx
            if days_ahead <= 0:
                days_ahead += 7
            # 'this' should prefer the same week if forward, otherwise next
            if prefix == 'this' and days_ahead < 7:
                return (base + timedelta(days=days_ahead)).isoformat()
            return (base + timedelta(days=days_ahead)).isoformat()

        if clean in weekdays:
            target_idx = weekdays.index(clean)
            current_idx = base.weekday()
            days_ahead = target_idx - current_idx
            if days_ahead <= 0:
                days_ahead += 7
            return (base + timedelta(days=days_ahead)).isoformat()

        rel = re.match(r"in\s+(\d+)\s+(day|week|month)s?", clean)
        if rel:
            num = int(rel.group(1))
            unit = rel.group(2)
            days = num if unit == "day" else (num * 7 if unit == "week" else num * 30)
            return (base + timedelta(days=days)).isoformat()
    except Exception:
        pass


def normalize_priority(raw: str) -> str:
    """Normalize a priority keyword to the canonical priority value."""
    return PRIORITY_MAP.get(raw.lower(), raw)


def clean_text(text: str) -> str:
    """Remove filler phrases and normalize whitespace."""
    cleaned = _CLEANUP_RE.sub("", text)
    return re.sub(r"\s{2,}", " ", cleaned).strip()
