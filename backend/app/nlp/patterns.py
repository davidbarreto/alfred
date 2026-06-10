import re

# Constants for NLP enrichment
PRIORITY_MAP = {
    "high": "HIGH", "urgent": "HIGH", "urgently": "HIGH", "asap": "HIGH",
    "as soon as possible": "HIGH", "critical": "HIGH",
    "medium": "MEDIUM", "important": "MEDIUM",
    "low": "LOW", "low priority": "LOW", "not urgent": "LOW",
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