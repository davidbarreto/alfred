
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

import re

from app.nlp.normalizer import clean_text, normalize_date
from app.nlp.patterns import (
    _DATE_RE, _PRIORITY_RE, PRIORITY_MAP,
    _AMOUNT_RE, _MERCHANT_RE, _EXPENSE_INTENT_RE, _INCOME_INTENT_RE,
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