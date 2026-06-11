
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from app.nlp.normalizer import clean_text, normalize_date
from app.nlp.patterns import _DATE_RE, _PRIORITY_RE, PRIORITY_MAP


def extract_entities(text: str, base_date: Optional[datetime | date] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Extracts dates and priorities from a text string.
    Returns the cleaned text and a dictionary of extracted entities.
    """
    entities = {}
    current_text = text

    # Extract all priority occurrences and choose the strongest
    priority_matches = list(_PRIORITY_RE.finditer(current_text))
    if priority_matches:
        levels = set()
        for m in priority_matches:
            levels.add(PRIORITY_MAP.get(m.group(0).lower(), "medium"))
        # decide strongest level: HIGH > MEDIUM > LOW
        if "HIGH" in levels:
            entities["priority"] = "HIGH"
        elif "MEDIUM" in levels:
            entities["priority"] = "MEDIUM"
        else:
            entities["priority"] = "LOW"
        # remove all priority spans (reverse to keep indices valid)
        for m in reversed(priority_matches):
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