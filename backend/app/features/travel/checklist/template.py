"""Pure rules for the pre-trip checklist template stored in core.settings. No DB or IO.

Key format: `travel.checklist.<anchor>.<slug>`; the value is a signed day offset from the trip's start or end date.
"""
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

logger = logging.getLogger(__name__)

KEY_PREFIX = "travel.checklist."
SEEDED_KEY = "travel.checklist_seeded"

Anchor = Literal["start", "end"]
ANCHORS: tuple[Anchor, ...] = ("start", "end")

SLUG_PATTERN = re.compile(r"^[a-z0-9_-]+$")

# Written the first time the template is read; (anchor, slug, offset in days).
DEFAULT_ITEMS: tuple[tuple[Anchor, str, int], ...] = (
    ("start", "passport-validity", -60),
    ("start", "travel-insurance", -30),
    ("start", "currency", -14),
    ("start", "sim-or-esim", -7),
    ("start", "plug-adapter", -7),
    ("start", "online-check-in", -1),
    ("end", "link-trip-charges", 2),
    ("end", "unpack-and-laundry", 1),
)


@dataclass(frozen=True)
class ChecklistItem:
    anchor: Anchor
    slug: str
    offset_days: int

    @property
    def title(self) -> str:
        return self.slug.replace("-", " ").replace("_", " ")

    @property
    def key(self) -> str:
        return make_key(self.anchor, self.slug)


def make_key(anchor: str, slug: str) -> str:
    return f"{KEY_PREFIX}{anchor}.{slug}"


def parse_items(values: dict[str, str]) -> list[ChecklistItem]:
    """Template items from raw settings; malformed ones are skipped with a WARNING, never raised."""
    items: list[ChecklistItem] = []
    for key, raw in values.items():
        if not key.startswith(KEY_PREFIX):
            continue
        anchor, _, slug = key[len(KEY_PREFIX):].partition(".")
        if anchor not in ANCHORS or not slug:
            logger.warning("Checklist item ignored: key=%s has no valid anchor and name", key)
            continue
        try:
            offset = int(raw.strip())
        except ValueError:
            logger.warning("Checklist item ignored: key=%s value is not an integer", key)
            continue
        items.append(ChecklistItem(anchor, slug, offset))  # type: ignore[arg-type]
    return sorted(items, key=lambda i: (i.anchor != "start", i.offset_days, i.slug))


def due_date(item: ChecklistItem, start: date, end: date, today: date) -> date:
    """The anchor date plus the offset; a date already past is moved to today."""
    base = start if item.anchor == "start" else end
    return max(base + timedelta(days=item.offset_days), today)
