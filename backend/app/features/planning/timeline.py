"""Pure planning helpers: timelines, work/office totals, recurring due dates. No DB, no IO.

All arithmetic and comparisons go through UTC instants: two aware datetimes sharing one tzinfo
are compared and subtracted by wall clock, which is wrong across a DST change.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Sequence

from app.features.organizer.calendar_events.constants import effective_availability
from app.features.organizer.calendar_events.schemas import EventRead
from app.features.organizer.routines.expansion import (
    StepWindow,
    elapsed_minutes,
    expand_event_steps,
    localize,
    shift_minutes,
)
from app.features.organizer.tasks.recurrence import is_due_today, parse_byday
from app.features.planning.schemas import AllDayItem, RoutineBlock, TimelineItem
from app.shared.timezone import local_timezone

_UTC = timezone.utc


@dataclass(frozen=True)
class _Block:
    item: TimelineItem
    start: datetime  # UTC instant
    end: datetime  # UTC instant
    blocking: bool


def iso_local(moment: datetime) -> str:
    """ISO string in the configured zone with an explicit offset."""
    return moment.astimezone(local_timezone()).isoformat(timespec="seconds")


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Local midnight to the next local midnight, as aware datetimes (23-25 hours long)."""
    zone = local_timezone()
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def event_start_end(event: EventRead) -> tuple[datetime, datetime]:
    return localize(event.start_datetime), localize(event.end_datetime)


def is_timed(event: EventRead) -> bool:
    return not event.all_day


def events_for_day(events: Sequence[EventRead], day: date) -> list[EventRead]:
    """Timed events that start on `day` (local); an event that crosses midnight stays on its start day."""
    return [e for e in events if is_timed(e) and e.start_datetime.date() == day]


def all_day_for_day(events: Sequence[EventRead], day: date) -> list[AllDayItem]:
    return [
        AllDayItem(title=e.title, event_id=e.id)
        for e in events
        if e.all_day and e.start_datetime.date() <= day <= e.end_datetime.date()
    ]


def build_timeline(
    events: Sequence[EventRead],
    routines_by_id: dict[int, Any],
    note_titles: dict[int, str],
    day: date,
) -> tuple[list[TimelineItem], list[str]]:
    """Timeline for one day: events, routine steps around them and derived travel blocks, sorted by start.

    Returns the items and warnings for overlaps between things that occupy time (blocked events, travel
    and routine steps with a duration). Overlaps are only reported, never resolved.
    """
    blocks: list[_Block] = []
    for event in events_for_day(events, day):
        start, end = event_start_end(event)
        availability = effective_availability(event.availability, event.all_day)
        blocks.append(
            _Block(
                item=TimelineItem(
                    kind="event",
                    title=event.title,
                    start=iso_local(start),
                    end=iso_local(end),
                    event_id=event.id,
                    availability=availability,
                    presence=event.presence,
                    location=event.location,
                    tags=event.tags or None,
                    notification_profile=event.notification_profile,
                ),
                start=start.astimezone(_UTC),
                end=end.astimezone(_UTC),
                blocking=availability == "blocked",
            )
        )
        if event.travel_minutes > 0:
            blocks.extend(_travel_blocks(event, start, end))
        routine = routines_by_id.get(event.routine_id) if event.routine_id else None
        if routine is not None:
            blocks.extend(_step_blocks(event, routine, start, end, note_titles))

    blocks.sort(key=lambda b: (b.start, b.end))
    return [b.item for b in blocks], _overlap_warnings(blocks, day)


def _travel_blocks(event: EventRead, start: datetime, end: datetime) -> list[_Block]:
    before_start = shift_minutes(start, -event.travel_minutes)
    after_end = shift_minutes(end, event.travel_minutes)
    legs = [
        (f"Travel to {event.title}", before_start, start),
        (f"Travel home from {event.title}", end, after_end),
    ]
    return [
        _Block(
            item=TimelineItem(kind="travel", title=title, start=iso_local(a), end=iso_local(b), event_id=event.id),
            start=a.astimezone(_UTC),
            end=b.astimezone(_UTC),
            blocking=True,
        )
        for title, a, b in legs
    ]


def _step_blocks(
    event: EventRead, routine: Any, start: datetime, end: datetime, note_titles: dict[int, str]
) -> list[_Block]:
    blocks = []
    for occurrence in expand_event_steps(routine.steps, start, end):
        blocks.append(
            _Block(
                item=TimelineItem(
                    kind="routine_step",
                    title=occurrence.title,
                    start=iso_local(occurrence.start),
                    end=iso_local(occurrence.end),
                    event_id=event.id,
                    routine_step_id=occurrence.step_id,
                    context=occurrence.context,
                    location=occurrence.location,
                    checklist_note_id=occurrence.checklist_note_id,
                    checklist_note_title=note_titles.get(occurrence.checklist_note_id)
                    if occurrence.checklist_note_id
                    else None,
                ),
                start=occurrence.start.astimezone(_UTC),
                end=occurrence.end.astimezone(_UTC),
                blocking=occurrence.duration_minutes > 0,
            )
        )
    return blocks


def _overlap_warnings(blocks: Sequence[_Block], day: date) -> list[str]:
    occupying = [b for b in blocks if b.blocking]
    warnings = []
    for index, first in enumerate(occupying):
        for second in occupying[index + 1:]:
            if second.start >= first.end:
                continue
            if first.start < second.end and second.start < first.end:
                warnings.append(
                    f"Overlap on {day.isoformat()}: '{first.item.title}' ({_hh_mm(first.item.start)}-{_hh_mm(first.item.end)})"
                    f" overlaps '{second.item.title}' ({_hh_mm(second.item.start)}-{_hh_mm(second.item.end)})."
                )
    return warnings


def _hh_mm(iso: str) -> str:
    return iso[11:16]


def routine_blocks_for(
    routine_name: str, windows: Sequence[StepWindow], note_titles: dict[int, str]
) -> list[RoutineBlock]:
    return [
        RoutineBlock(
            routine=routine_name,
            routine_step_id=w.step_id,
            title=w.title,
            duration_minutes=w.duration_minutes,
            window=f"{w.window_start.strftime('%H:%M')}-{w.window_end.strftime('%H:%M')}",
            fixed=True if w.fixed else None,
            context=w.context,
            location=w.location,
            checklist_note_id=w.checklist_note_id,
            checklist_note_title=note_titles.get(w.checklist_note_id) if w.checklist_note_id else None,
        )
        for w in windows
    ]


def has_tag(event: EventRead, tag: str) -> bool:
    return tag.lower() in {t.lower() for t in event.tags}


def committed_work_minutes(
    events: Sequence[EventRead], day: date, work_tag: str, task_blocks: Sequence[tuple[datetime, datetime]] = ()
) -> int:
    """Real minutes taken by timed events tagged `work_tag` that start on `day`, plus the saved work-task blocks.

    Time covered by more than one of them counts once.
    """
    spans = [event_start_end(e) for e in events_for_day(events, day) if has_tag(e, work_tag)]
    return merged_minutes([*spans, *task_blocks])


def merged_minutes(spans: Sequence[tuple[datetime, datetime]]) -> int:
    """Minutes covered by the union of the spans, measured on UTC instants so a DST day is not off by an hour."""
    instants = sorted((start.astimezone(_UTC), end.astimezone(_UTC)) for start, end in spans)
    total = 0
    covered_until: datetime | None = None
    for start, end in instants:
        if covered_until is not None and start < covered_until:
            start = covered_until
        if end > start:
            total += elapsed_minutes(start, end)
            covered_until = end
    return total


def office_days(events: Sequence[EventRead], office_tag: str, min_minutes: int) -> set[date]:
    """Local dates with an in-person timed event tagged `office_tag` lasting at least `min_minutes`."""
    days = set()
    for event in events:
        if not is_timed(event) or event.presence != "in_person" or not has_tag(event, office_tag):
            continue
        start, end = event_start_end(event)
        if elapsed_minutes(start, end) >= min_minutes:
            days.add(event.start_datetime.date())
    return days


def week_bounds(day: date) -> tuple[date, date]:
    """Monday and Sunday of the ISO week containing `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def days_left_in_week(day: date) -> int:
    """Days from `day` through Sunday, inclusive."""
    return 7 - day.weekday()


def is_flexible_cadence(recurrence_rule: str) -> bool:
    """True when the rule has no specific due day (monthly, or weekly without BYDAY)."""
    if "FREQ=DAILY" in recurrence_rule:
        return False
    if "FREQ=WEEKLY" in recurrence_rule and parse_byday(recurrence_rule):
        return False
    return True


def recurring_due_dates(recurrence_rule: str, days: Sequence[date]) -> list[date]:
    """Requested dates a day-specific recurring task falls on (BYDAY weekly, or daily)."""
    return [d for d in days if is_due_today(recurrence_rule, d)]
