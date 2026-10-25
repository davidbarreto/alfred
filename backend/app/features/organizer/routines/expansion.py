"""Pure expansion of routine steps into concrete times. No DB, no IO."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol, Sequence

from dateutil.rrule import rrulestr

from app.shared.timezone import local_timezone

_MAX_DATES = 400
_UTC = timezone.utc


class StepLike(Protocol):
    id: int
    title: str
    duration_minutes: int
    anchor: str | None
    offset_minutes: int | None
    window_start: time | None
    window_end: time | None
    context: str | None
    location: str | None
    checklist_note_id: int | None


@dataclass(frozen=True)
class StepOccurrence:
    """A step of an event-attached routine, placed relative to one event occurrence."""

    step_id: int
    title: str
    start: datetime
    end: datetime
    duration_minutes: int
    context: str | None
    location: str | None
    checklist_note_id: int | None


@dataclass(frozen=True)
class StepWindow:
    """A step of a scheduled routine on one date: it happens inside the window; Claude places it."""

    step_id: int
    day: date
    title: str
    duration_minutes: int
    window_start: time
    window_end: time
    context: str | None
    location: str | None
    checklist_note_id: int | None

    @property
    def fixed(self) -> bool:
        """A window exactly as long as the step is a fixed time."""
        span = datetime.combine(self.day, self.window_end) - datetime.combine(self.day, self.window_start)
        return span == timedelta(minutes=self.duration_minutes)


def localize(naive: datetime) -> datetime:
    """Attach the configured local zone to a naive local datetime (as stored/expanded elsewhere)."""
    return naive.replace(tzinfo=local_timezone()) if naive.tzinfo is None else naive


def shift_minutes(moment: datetime, minutes: int) -> datetime:
    """Add real elapsed minutes to an aware datetime; goes through UTC so DST changes can't skew it."""
    return (moment.astimezone(_UTC) + timedelta(minutes=minutes)).astimezone(moment.tzinfo)


def elapsed_minutes(start: datetime, end: datetime) -> int:
    """Real minutes between two aware datetimes. Subtracting them directly would ignore the UTC
    offsets when both carry the same tzinfo, which is wrong across a DST change."""
    return int((end.astimezone(_UTC) - start.astimezone(_UTC)).total_seconds() // 60)


def expand_event_steps(
    steps: Sequence[StepLike], event_start: datetime, event_end: datetime
) -> list[StepOccurrence]:
    """Place anchor+offset steps around one event occurrence; steps in window form are ignored."""
    occurrences = []
    for step in steps:
        if step.anchor is None or step.offset_minutes is None:
            continue
        anchor = event_start if step.anchor == "start" else event_end
        start = shift_minutes(anchor, step.offset_minutes)
        occurrences.append(
            StepOccurrence(
                step_id=step.id,
                title=step.title,
                start=start,
                end=shift_minutes(start, step.duration_minutes),
                duration_minutes=step.duration_minutes,
                context=step.context,
                location=step.location,
                checklist_note_id=step.checklist_note_id,
            )
        )
    return sorted(occurrences, key=lambda o: o.start)


def parse_recurrence(recurrence_rule: str, starts_on: date):
    """Parse an RRULE anchored at midnight of `starts_on` (raises ValueError when invalid)."""
    return rrulestr(recurrence_rule, dtstart=datetime.combine(starts_on, time.min))


def scheduled_dates(recurrence_rule: str, starts_on: date, range_start: date, range_end: date) -> list[date]:
    """Dates in [range_start, range_end] on which a scheduled routine runs (COUNT/UNTIL honoured)."""
    rule = parse_recurrence(recurrence_rule, starts_on)
    first = datetime.combine(range_start, time.min)
    last = datetime.combine(range_end, time.max)
    days = {moment.date() for moment in rule.between(first, last, inc=True)}
    return sorted(days)[:_MAX_DATES]


def expand_scheduled_steps(steps: Sequence[StepLike], days: Sequence[date]) -> list[StepWindow]:
    """One StepWindow per window-form step per day; anchor-form steps are ignored."""
    windows = []
    for day in days:
        for step in steps:
            if step.window_start is None or step.window_end is None:
                continue
            windows.append(
                StepWindow(
                    step_id=step.id,
                    day=day,
                    title=step.title,
                    duration_minutes=step.duration_minutes,
                    window_start=step.window_start,
                    window_end=step.window_end,
                    context=step.context,
                    location=step.location,
                    checklist_note_id=step.checklist_note_id,
                )
            )
    return windows
