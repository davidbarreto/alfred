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
from app.features.planning.schemas import AllDayItem, RoutineBlock, TimelineItem, TravelOption
from app.shared.utils.timezone import local_timezone

_UTC = timezone.utc


@dataclass(frozen=True)
class _Block:
    item: TimelineItem
    start: datetime  # UTC instant
    end: datetime  # UTC instant
    blocking: bool
    container: bool = False  # an in-person office event: meetings inside it are not overlaps


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
) -> "DayTimeline":
    """Timeline for one day: events, routine steps around them and derived travel blocks, sorted by start.

    Also returns warnings for overlaps between things that occupy time (blocked events, travel and routine
    steps with a duration) and for assumed travel. Overlaps are only reported, never resolved. Something that
    sits entirely inside an in-person event tagged `office_tag` (a standup during an office day) is not one.
    Travel comes from `graph` (see `_travel_blocks`); without one only events' own travel minutes count.
    """
    graph = graph or TravelGraph()
    day_events = sorted(events_for_day(events, day), key=lambda e: (e.start_datetime, e.end_datetime, e.id))
    blocks: list[_Block] = []
    for event in day_events:
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
                    location=graph.name(event.location_id) if event.location_id is not None else event.location,
                    location_id=event.location_id,
                    tags=event.tags or None,
                    notification_profile=event.notification_profile,
                ),
                start=start.astimezone(_UTC),
                end=end.astimezone(_UTC),
                blocking=availability == "blocked",
                container=_is_office_event(event, office_tag),
            )
        )
        routine = routines_by_id.get(event.routine_id) if event.routine_id else None
        if routine is not None:
            blocks.extend(_step_blocks(event, routine, start, end, note_titles))

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

_WALKING_MODES = frozenset({"foot", "walk", "walking"})
_CAR_MODES = frozenset({"car", "taxi"})


def mode_class(mode: str) -> str:
    """walking, car or public: every mode name that is not walking or a car (metro, bus, train...) is public."""
    if mode in _WALKING_MODES:
        return "walking"
    if mode in _CAR_MODES:
        return "car"
    return "public"


def choose_option(options: Sequence[TravelOption], walk_tolerance: int) -> TravelOption:
    """The fastest public transport, unless walking takes at most `walk_tolerance` minutes more; car only alone."""
    def fastest(kind: str) -> TravelOption | None:
        matching = [o for o in options if mode_class(o.mode) == kind]
        return min(matching, key=lambda o: o.minutes) if matching else None

    public, walking = fastest("public"), fastest("walking")
    if public is not None:
        return walking if walking is not None and walking.minutes <= public.minutes + walk_tolerance else public
    return walking or fastest("car")  # type: ignore[return-value]


@dataclass(frozen=True)
class TravelGraph:
    """The user's locations and the travel times between them, plus the planning defaults for travel."""

    names: dict[int, str] = field(default_factory=dict)
    home_id: int | None = None
    # (origin id, destination id) -> {mode: minutes}; a route counts both ways unless the reverse is saved too.
    routes: dict[tuple[int, int], dict[str, int]] = field(default_factory=dict)
    # One-way minutes assumed when nothing is known; 0 switches the assumption off.
    default_minutes: int = 0
    walk_tolerance: int = 10

    def name(self, location_id: int | None) -> str:
        """None stands for home when there is no Home location."""
        if location_id is None:
            return "Home"
        return self.names.get(location_id, "Home" if location_id == self.home_id else f"Location {location_id}")

    def options(self, origin: int | None, destination: int | None) -> list[TravelOption]:
        if origin is None or destination is None:
            return []
        forward = self.routes.get((origin, destination), {})
        backward = self.routes.get((destination, origin), {})
        merged = {**backward, **forward}
        return sorted((TravelOption(mode=m, minutes=n) for m, n in merged.items()), key=lambda o: (o.minutes, o.mode))


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

    In-person events at a location form a chain: Home -> first place -> next place ... -> Home, one block per
    change of place (two events at the same place need none). An event inside another located event (a lunch
    out during an office day) goes there and back from that event's place. Events without a location keep their
    own travel minutes to and from home; with none, the default is assumed for in-person events unless they are
    all-day, free, or inside an office or located in-person event. Minutes come from the pair's travel times,
    else the event's travel minutes, else the default (marked assumed, with one warning per pair).
    """
    spans = [_Span(e, *event_start_end(e)) for e in day_events]
    located = [s for s in spans if _is_located(s.event)]
    outer = [s for i, s in enumerate(located) if _container_of(s, i, located) is None]
    legs = _Legs(graph)

    current: int | None = graph.home_id
    for span in outer:
        legs.add(current, span.event.location_id, span, arrive=True)
        current = span.event.location_id
    if outer:
        legs.add(current, graph.home_id, outer[-1], arrive=False)

    for index, span in enumerate(located):
        container = _container_of(span, index, located)
        if container is not None:
            legs.add(container.event.location_id, span.event.location_id, span, arrive=True)
            legs.add(span.event.location_id, container.event.location_id, span, arrive=False)

    assumed: list[tuple[int, str]] = []
    containers = [s for s in spans if _is_office_event(s.event, office_tag) or _is_located(s.event)]
    for span in spans:
        event = span.event
        if event.location_id is not None:
            continue
        if event.travel_minutes > 0:
            legs.home_trip(span, event.travel_minutes, assumed=False)
        elif graph.default_minutes > 0 and _needs_assumed_travel(span, containers):
            legs.home_trip(span, graph.default_minutes, assumed=True)
            assumed.append((event.id, event.title))
    return legs.blocks, legs.warnings, assumed


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


def _container_of(span: _Span, index: int, located: Sequence[_Span]) -> _Span | None:
    """The first located event that holds `span` entirely (of two identical spans, the earlier holds the later)."""
    for other_index, other in enumerate(located):
        if other_index == index:
            continue
        if other.start_utc <= span.start_utc and span.end_utc <= other.end_utc:
            same = other.start_utc == span.start_utc and other.end_utc == span.end_utc
            if not same or other_index < index:
                return other
    return None


class _Legs:
    """Collects travel blocks and the assumed-travel warnings (one per pair of places and day)."""

    def __init__(self, graph: TravelGraph) -> None:
        self._graph = graph
        self.blocks: list[_Block] = []
        self.warnings: list[str] = []
        self._warned: set[frozenset] = set()

    def add(self, origin: int | None, destination: int | None, span: _Span, arrive: bool) -> None:
        """A trip between two places that ends when `span` starts (arrive) or starts when it ends."""
        if origin == destination:
            return
        graph = self._graph
        names = f"{graph.name(origin)} → {graph.name(destination)}"
        options = graph.options(origin, destination)
        assumed = False
        if options:
            chosen = choose_option(options, graph.walk_tolerance)
            minutes, title = chosen.minutes, f"{names} ({chosen.mode}, {chosen.minutes})"
        elif span.event.travel_minutes > 0:
            minutes, title = span.event.travel_minutes, f"{names} ({span.event.travel_minutes})"
        elif graph.default_minutes > 0:
            minutes, title, assumed = graph.default_minutes, f"{names} (assumed {graph.default_minutes})", True
            pair = frozenset((origin, destination))
            if pair not in self._warned:
                self._warned.add(pair)
                self.warnings.append(
                    f"Assumed {minutes} min from {graph.name(origin)} to {graph.name(destination)}: "
                    "no travel time saved"
                )
        else:
            return
        start, end = (shift_minutes(span.start, -minutes), span.start) if arrive else (span.end, shift_minutes(span.end, minutes))
        self._append(title, start, end, span.event.id, options or None, assumed)

    def home_trip(self, span: _Span, minutes: int, assumed: bool) -> None:
        """To an event with no location and back home, `minutes` each way."""
        title = span.event.title
        self._append(f"Travel to {title}", shift_minutes(span.start, -minutes), span.start, span.event.id, None, assumed)
        self._append(f"Travel home from {title}", span.end, shift_minutes(span.end, minutes), span.event.id, None, assumed)

    def _append(
        self, title: str, start: datetime, end: datetime, event_id: int,
        options: list[TravelOption] | None, assumed: bool,
    ) -> None:
        self.blocks.append(
            _Block(
                item=TimelineItem(
                    kind="travel", title=title, start=iso_local(start), end=iso_local(end), event_id=event_id,
                    options=options, assumed=True if assumed else None,
                ),
                start=start.astimezone(_UTC),
                end=end.astimezone(_UTC),
                blocking=True,
            )
        )


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
                if _inside_container(first, second) or _inside_container(second, first):
                    continue
                warnings.append(
                    f"Overlap on {day.isoformat()}: '{first.item.title}' ({_hh_mm(first.item.start)}-{_hh_mm(first.item.end)})"
                    f" overlaps '{second.item.title}' ({_hh_mm(second.item.start)}-{_hh_mm(second.item.end)})."
                )
    return warnings


def _inside_container(inner: _Block, outer: _Block) -> bool:
    return outer.container and not inner.container and outer.start <= inner.start and inner.end <= outer.end


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
