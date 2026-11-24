"""Pure planning helpers: timelines, work/office totals, recurring due dates. No DB, no IO.

All arithmetic and comparisons go through UTC instants: two aware datetimes sharing one tzinfo
are compared and subtracted by wall clock, which is wrong across a DST change.
"""
from dataclasses import dataclass, field
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
from app.shared.utils.timezone import local_timezone

_UTC = timezone.utc


@dataclass(frozen=True)
class _Block:
    item: TimelineItem
    start: datetime  # UTC instant
    end: datetime  # UTC instant
    blocking: bool
    container: bool = False  # an in-person office event: work inside it is not an overlap
    work: bool = False  # a work-tagged event or one of its routine steps


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
    office_tag: str | None = None,
    graph: "TravelGraph | None" = None,
    work_tag: str | None = None,
) -> "DayTimeline":
    """Timeline for one day: events, routine steps around them and travel of unlocated events, sorted by start.

    Also returns warnings for overlaps between things that occupy time (blocked events, travel and routine
    steps with a duration) and for assumed travel. Overlaps are only reported, never resolved. A work-tagged event
    (or one of its steps) entirely inside an in-person event tagged `office_tag` (a standup during an office day) is
    not one; anything else inside it (a personal appointment) is.
    Travel comes from `graph` (see `_travel_blocks`); without one only events' own travel minutes count.
    """
    graph = graph or TravelGraph()
    day_events = sorted(events_for_day(events, day), key=lambda e: (e.start_datetime, e.end_datetime, e.id))
    blocks: list[_Block] = []
    for event in day_events:
        start, end = event_start_end(event)
        availability = effective_availability(event.availability, event.all_day)
        work = bool(work_tag) and has_tag(event, work_tag)
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
                    location=graph.name(event.location_id) if event.location_id is not None else event.location,
                    location_id=event.location_id,
                    tags=event.tags or None,
                    notification_profile=event.notification_profile,
                ),
                start=start.astimezone(_UTC),
                end=end.astimezone(_UTC),
                blocking=availability == "blocked",
                container=_is_office_event(event, office_tag),
                work=work,
            )
        )
        routine = routines_by_id.get(event.routine_id) if event.routine_id else None
        if routine is not None:
            blocks.extend(_step_blocks(event, routine, start, end, note_titles, work))

    travel, travel_warnings, assumed = _travel_blocks(day_events, graph, office_tag)
    blocks.extend(travel)
    blocks.sort(key=lambda b: (b.start, b.end))
    return DayTimeline(
        items=[b.item for b in blocks],
        warnings=[*travel_warnings, *_overlap_warnings(blocks, day)],
        assumed_events=assumed,
    )


def _is_office_event(event: EventRead, office_tag: str | None) -> bool:
    return bool(office_tag) and event.presence == "in_person" and has_tag(event, office_tag)


# --- derived travel ------------------------------------------------------------------------


@dataclass(frozen=True)
class TravelGraph:
    """The user's locations, which pairs have a saved travel time, and the minutes assumed when nothing is known."""

    names: dict[int, str] = field(default_factory=dict)
    home_id: int | None = None
    # (origin id, destination id) of every saved travel time; a route counts both ways.
    routes: frozenset[tuple[int, int]] = frozenset()
    # One-way minutes assumed when nothing is known; 0 switches the assumption off.
    default_minutes: int = 0

    def name(self, location_id: int | None) -> str:
        """None stands for home when there is no Home location."""
        if location_id is None:
            return "Home"
        return self.names.get(location_id, "Home" if location_id == self.home_id else f"Location {location_id}")

    def connected(self, origin: int, destination: int) -> bool:
        return (origin, destination) in self.routes or (destination, origin) in self.routes


@dataclass(frozen=True)
class DayTimeline:
    items: list[TimelineItem]
    warnings: list[str]
    # In-person events with no location and no travel minutes whose travel was assumed: (event id, title).
    assumed_events: list[tuple[int, str]]


@dataclass(frozen=True)
class _Span:
    event: EventRead
    start: datetime  # local, aware
    end: datetime

    @property
    def start_utc(self) -> datetime:
        return self.start.astimezone(_UTC)

    @property
    def end_utc(self) -> datetime:
        return self.end.astimezone(_UTC)


def _travel_blocks(
    day_events: Sequence[EventRead], graph: TravelGraph, office_tag: str | None
) -> tuple[list[_Block], list[str], list[tuple[int, str]]]:
    """Travel for one day's events (sorted by start).

    Events at a location get no blocks: the route between places (and the stops between them) is the client's to
    decide from the travel times in the preferences. Each place an in-person event goes to with no saved travel time
    from Home gets a warning. Events without a location keep their own travel minutes to and from home; with none,
    the default is assumed for in-person events unless they are all-day, free, or inside an office or located event.
    """
    spans = [_Span(e, *event_start_end(e)) for e in day_events]
    blocks: list[_Block] = []
    warnings: list[str] = []
    for place in dict.fromkeys(s.event.location_id for s in spans if _is_located(s.event)):
        if graph.home_id is None:
            warnings.append(f"No Home location saved: travel from home to {graph.name(place)} is unknown")
        elif place != graph.home_id and not graph.connected(graph.home_id, place):
            warnings.append(
                f"No travel time saved between {graph.name(graph.home_id)} and {graph.name(place)}: "
                "ask the user and offer to save it"
            )

    assumed: list[tuple[int, str]] = []
    containers = [s for s in spans if _is_office_event(s.event, office_tag) or _is_located(s.event)]
    for span in spans:
        event = span.event
        if event.location_id is not None:
            continue
        if event.travel_minutes > 0:
            blocks.extend(_home_trip(span, event.travel_minutes, assumed=False))
        elif graph.default_minutes > 0 and _needs_assumed_travel(span, containers):
            blocks.extend(_home_trip(span, graph.default_minutes, assumed=True))
            assumed.append((event.id, event.title))
    return blocks, warnings, assumed


def _is_located(event: EventRead) -> bool:
    """At a location and occupying the user there: in person and not free."""
    return (
        event.location_id is not None
        and event.presence == "in_person"
        and effective_availability(event.availability, event.all_day) != "free"
    )


def _needs_assumed_travel(span: _Span, containers: Sequence[_Span]) -> bool:
    event = span.event
    if event.presence != "in_person" or effective_availability(event.availability, event.all_day) == "free":
        return False
    return not any(
        other.event is not event and other.start_utc <= span.start_utc and span.end_utc <= other.end_utc
        for other in containers
    )


def _home_trip(span: _Span, minutes: int, assumed: bool) -> list[_Block]:
    """To an event with no location and back home, `minutes` each way."""
    title = span.event.title
    return [
        _travel_block(f"Travel to {title}", shift_minutes(span.start, -minutes), span.start, span.event.id, assumed),
        _travel_block(f"Travel home from {title}", span.end, shift_minutes(span.end, minutes), span.event.id, assumed),
    ]


def _travel_block(title: str, start: datetime, end: datetime, event_id: int, assumed: bool) -> _Block:
    return _Block(
        item=TimelineItem(
            kind="travel", title=title, start=iso_local(start), end=iso_local(end), event_id=event_id,
            assumed=True if assumed else None,
        ),
        start=start.astimezone(_UTC),
        end=end.astimezone(_UTC),
        blocking=True,
    )


def _step_blocks(
    event: EventRead, routine: Any, start: datetime, end: datetime, note_titles: dict[int, str], work: bool
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
                work=work,
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
                if _inside_container(first, second) or _inside_container(second, first):
                    continue
                warnings.append(
                    f"Overlap on {day.isoformat()}: '{first.item.title}' ({_hh_mm(first.item.start)}-{_hh_mm(first.item.end)})"
                    f" overlaps '{second.item.title}' ({_hh_mm(second.item.start)}-{_hh_mm(second.item.end)})."
                )
    return warnings


def _inside_container(inner: _Block, outer: _Block) -> bool:
    return (
        outer.container
        and inner.work
        and not inner.container
        and outer.start <= inner.start
        and inner.end <= outer.end
    )


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
