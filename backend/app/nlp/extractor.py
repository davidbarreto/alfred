
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

import re

from app.nlp.normalizer import clean_text, normalize_date
from app.nlp.patterns import (
    _DATE_RE, _PRIORITY_RE, PRIORITY_MAP,
    _AMOUNT_RE, _MERCHANT_RE, _EXPENSE_INTENT_RE, _INCOME_INTENT_RE,
    _TIME_RANGE_RE, _TIME_SINGLE_RE,
)

_CURRENCY_SYMBOL_MAP = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
_CURRENCY_WORD_MAP = {
    "dollar": "USD", "dollars": "USD", "buck": "USD", "bucks": "USD",
    "euro": "EUR", "euros": "EUR",
    "pound": "GBP", "pounds": "GBP",
    "yen": "JPY",
}


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


def _parse_time_token(token: str) -> Optional[Tuple[int, int]]:
    """Parse a time-of-day token ('19h', '19h30', '19:00', '7pm', '7:30pm') to (hour, minute)."""
    m = re.match(r'^\s*(\d{1,2})(?:[:h](\d{2})|h)?\s*(am|pm)?\s*$', token.strip(), re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def extract_time_range(text: str) -> Tuple[str, Dict[str, str]]:
    """
    Extract a start/end time-of-day ('HH:MM') from phrases like 'from 19h to 21h'
    or a single 'at 7pm'. Returns the text with the matched phrase removed.
    """
    entities: Dict[str, str] = {}

    range_match = _TIME_RANGE_RE.search(text)
    if range_match:
        start_hm = _parse_time_token(range_match.group(1))
        end_hm = _parse_time_token(range_match.group(2))
        if start_hm:
            entities["start_time"] = f"{start_hm[0]:02d}:{start_hm[1]:02d}"
        if end_hm:
            entities["end_time"] = f"{end_hm[0]:02d}:{end_hm[1]:02d}"
        current_text = text[:range_match.start()] + text[range_match.end():]
        return clean_text(current_text), entities

    single_match = _TIME_SINGLE_RE.search(text)
    if single_match:
        token = single_match.group(1) or single_match.group(2)
        hm = _parse_time_token(token)
        if hm:
            entities["start_time"] = f"{hm[0]:02d}:{hm[1]:02d}"
        current_text = text[:single_match.start()] + text[single_match.end():]
        return clean_text(current_text), entities

    return clean_text(text), entities


def extract_finance_entities(text: str, base_date: Optional[datetime | date] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Extract finance entities (amount, currency, merchant, type, date) from text.
    Returns the original text unchanged and a dict of extracted entities.
    """
    entities: Dict[str, Any] = {}
    effective_base: datetime = (
        base_date if isinstance(base_date, datetime)
        else datetime.combine(base_date, datetime.min.time()) if base_date
        else datetime.now()
    )

    m = _AMOUNT_RE.search(text)
    if m:
        raw = (m.group(1) or m.group(2)).replace(",", ".")
        entities["amount"] = float(raw)
        full = m.group(0)
        for sym, code in _CURRENCY_SYMBOL_MAP.items():
            if sym in full:
                entities["currency"] = code
                break
        else:
            word = re.search(r'\b(euros?|dollars?|pounds?|bucks?|yen)\b', text, re.IGNORECASE)
            if word:
                entities["currency"] = _CURRENCY_WORD_MAP.get(word.group(1).lower())

    m = _MERCHANT_RE.search(text)
    if m:
        entities["merchant"] = m.group(1).strip()

    if _EXPENSE_INTENT_RE.search(text):
        entities["type"] = "expense"
    elif _INCOME_INTENT_RE.search(text):
        entities["type"] = "income"

    date_match = _DATE_RE.search(text)
    if date_match:
        entities["date"] = normalize_date(date_match.group(0), base_date=effective_base)

    return text, entities