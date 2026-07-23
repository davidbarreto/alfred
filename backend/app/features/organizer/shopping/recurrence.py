from __future__ import annotations

from datetime import datetime, timezone


def is_recurrence_due(last_added_at: datetime | None, recurrence_days: int, now: datetime | None = None) -> bool:
    if last_added_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - last_added_at).days >= recurrence_days
