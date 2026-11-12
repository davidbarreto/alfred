"""Pure helpers for /tnote: which visit a quick note belongs to, and how it is appended. No DB or IO."""
from datetime import datetime, time

from app.features.travel.visits.schemas import VisitRead


def pick_note_visit(visits: list[VisitRead], local_now: datetime) -> VisitRead | None:
    """The latest visit whose day and time are already past (a visit with no time counts from the start of its day).

    Missed visits never receive a note."""
    started = [
        v for v in visits
        if v.visit_date is not None and v.status != "missed"
        and datetime.combine(v.visit_date, v.visit_time or time.min) <= local_now
    ]
    return max(started, key=lambda v: (v.visit_date, v.visit_time or time.min, v.id), default=None)


def append_note(notes: str | None, local_now: datetime, text: str) -> str:
    line = f"[{local_now:%Y-%m-%d %H:%M}] {text.strip()}"
    return f"{notes.rstrip()}\n{line}" if notes and notes.strip() else line
