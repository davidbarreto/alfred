import re
from datetime import datetime, date
from typing import Dict, Any, Tuple, Optional
import dateparser

# Constants for NLP enrichment
PRIORITY_MAP = {
    "urgent": "high", "urgently": "high", "asap": "high",
    "as soon as possible": "high", "critical": "high",
    "important": "medium",
    "low priority": "low", "not urgent": "low",
}

_DATE_HINTS = [
    r"\b(today|tomorrow|yesterday)\b",
    r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(?:next|this)\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    r"\b(next\s+week|this\s+week|next\s+month)\b",
    r"\b(in\s+\d+\s+(days?|weeks?|months?))\b",
    r"\b(on|by|due|at)\s+(?:today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next\s+week|this\s+week|next\s+month|in\s+\d+\s+(?:days?|weeks?|months?)|\d{1,2}/\d{1,2}(?:/\d{2,4})?|\d{4}-\d{2}-\d{2})\b",
    r"\b\d{1,2}/\d{1,2}(/\d{2,4})?\b",
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\b",
]

_DATE_RE = re.compile("|".join(_DATE_HINTS), re.IGNORECASE)
_PRIORITY_RE = re.compile("|".join([rf"\b{k}\b" for k in PRIORITY_MAP.keys()]), re.IGNORECASE)
_CLEANUP_RE = re.compile(
    r"^(?:\s*(?:i need to|i have to|i must|i should|remind me to|don't forget to|please|can you|could you|remember to|make sure to)\s+)|"
    r"(?:\s+(?:please|thanks|thank you)\s*$)|"
    r"\b(?:on|at|for|by|due|priority:?)\b",
    re.IGNORECASE
)

def normalize_date(raw: str, base_date: Optional[datetime | date] = None) -> Optional[str]:
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

def extract_entities(text: str, base_date: Optional[datetime | date] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts dates and priorities from a text string.
    Returns the cleaned text and a dictionary of extracted entities.
    """
    entities = {}
    current_text = text

    # Extract all priority occurrences and choose the strongest
    prio_matches = list(_PRIORITY_RE.finditer(current_text))
    if prio_matches:
        levels = set()
        for m in prio_matches:
            levels.add(PRIORITY_MAP.get(m.group(0).lower(), "medium"))
        # decide strongest level: high > medium > low
        if "high" in levels:
            entities["priority"] = "high"
        elif "medium" in levels:
            entities["priority"] = "medium"
        else:
            entities["priority"] = "low"
        # remove all priority spans (reverse to keep indices valid)
        for m in reversed(prio_matches):
            current_text = current_text[:m.start()] + current_text[m.end():]

    # Extract first deadline-like phrase
    date_match = _DATE_RE.search(current_text)
    if date_match:
        iso_text = date_match.group(0)
        # ensure a concrete base_date for relative parsing
        effective_base = base_date if base_date is not None else datetime.now()
        iso_date = normalize_date(iso_text, base_date=effective_base)
        if iso_date:
            entities["deadline"] = iso_date
        # remove the matched date phrase from the text regardless of normalization
        current_text = current_text[:date_match.start()] + current_text[date_match.end():]

    return clean_text(current_text), entities