from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.features.organizer.calendar_events.schemas import EventRead
from app.features.organizer.routines.expansion import StepWindow
from app.features.planning import timeline

LISBON = ZoneInfo("Europe/Lisbon")
WED = date(2026, 10, 21)


def _event(id=1, title="Event", start=(2026, 10, 21, 10, 0), end=(2026, 10, 21, 11, 0), **kw) -> EventRead:
    return EventRead(
        id=id, title=title, start_datetime=datetime(*start), end_datetime=datetime(*end),
        tags=kw.pop("tags", []), **kw,
    )


def _step(id, title, anchor=None, offset=None, duration=0, **kw):
    return SimpleNamespace(
        id=id, title=title, anchor=anchor, offset_minutes=offset, duration_minutes=duration,
        window_start=None, window_end=None, context=kw.get("context"), location=kw.get("location"),
        checklist_note_id=kw.get("note"),
    )


class TestDayBounds:
    def test_normal_day_is_24_hours(self):
        start, end = timeline.day_bounds(date(2026, 10, 21))
        assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)) == timedelta(hours=24)

    def test_autumn_change_day_is_25_hours(self):
        start, end = timeline.day_bounds(date(2026, 10, 25))
        assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)) == timedelta(hours=25)

    def test_spring_change_day_is_23_hours(self):
        start, end = timeline.day_bounds(date(2026, 3, 29))
        assert (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)) == timedelta(hours=23)


class TestBuildTimeline:
    def test_events_are_sorted_and_carry_offsets_and_planning_fields(self):
        events = [
            _event(2, "Late", (2026, 10, 21, 22, 0), (2026, 10, 21, 22, 30), presence="remote_home",
                   notification_profile="cant_miss"),
            _event(1, "Early", (2026, 10, 21, 10, 0), (2026, 10, 21, 10, 30), tags=["work"], location="Office"),
        ]

        items, warnings = timeline.build_timeline(events, {}, {}, WED)

        assert [i.title for i in items] == ["Early", "Late"]
        assert items[0].start == "2026-10-21T10:00:00+01:00"
        assert (items[0].kind, items[0].availability, items[0].presence) == ("event", "blocked", "in_person")
        assert items[0].tags == ["work"] and items[0].location == "Office"
        assert items[1].notification_profile == "cant_miss" and items[1].tags is None
        assert warnings == []

    def test_only_events_starting_that_day_are_included(self):
        events = [_event(1, "Today"), _event(2, "Tomorrow", (2026, 10, 22, 10, 0), (2026, 10, 22, 11, 0))]
        items, _ = timeline.build_timeline(events, {}, {}, WED)
        assert [i.title for i in items] == ["Today"]

    def test_all_day_events_are_not_on_the_timeline(self):
        events = [_event(1, "Holiday", (2026, 10, 21, 0, 0), (2026, 10, 21, 23, 59), all_day=True)]
        items, _ = timeline.build_timeline(events, {}, {}, WED)
        assert items == []

    def test_travel_blocks_surround_the_event(self):
        events = [_event(7, "Class", (2026, 10, 21, 20, 0), (2026, 10, 21, 21, 0), travel_minutes=25)]

        items, warnings = timeline.build_timeline(events, {}, {}, WED)

        assert [(i.kind, i.title, i.start[11:16], i.end[11:16]) for i in items] == [
            ("travel", "Travel to Class", "19:35", "20:00"),
            ("event", "Class", "20:00", "21:00"),
            ("travel", "Travel home from Class", "21:00", "21:25"),
        ]
        assert warnings == []

    def test_no_travel_blocks_without_travel_minutes(self):
        items, _ = timeline.build_timeline([_event()], {}, {}, WED)
        assert [i.kind for i in items] == ["event"]

    def test_routine_steps_are_placed_around_the_event(self):
        routine = SimpleNamespace(steps=[
            _step(101, "Prepare dinner", "start", -120, 40, context="home", note=26),
            _step(103, "Leave to pick up", "start", -50, 20, context="out", location="Course"),
        ])
        events = [_event(7, "Class", (2026, 10, 21, 20, 0), (2026, 10, 21, 21, 0), routine_id=3)]

        items, _ = timeline.build_timeline(events, {3: routine}, {26: "Dinner checklist"}, WED)

        steps = [i for i in items if i.kind == "routine_step"]
        assert [(s.title, s.start[11:16], s.end[11:16]) for s in steps] == [
            ("Prepare dinner", "18:00", "18:40"), ("Leave to pick up", "19:10", "19:30"),
        ]
        assert steps[0].checklist_note_id == 26 and steps[0].checklist_note_title == "Dinner checklist"
        assert steps[0].event_id == 7 and steps[0].routine_step_id == 101
        assert steps[1].location == "Course" and steps[1].context == "out"
        assert [i.kind for i in items][-1] == "event"

    def test_unknown_routine_id_is_ignored(self):
        events = [_event(7, routine_id=99)]
        items, _ = timeline.build_timeline(events, {}, {}, WED)
        assert [i.kind for i in items] == ["event"]

    def test_free_availability_is_reported_but_not_blocking(self):
        events = [
            _event(1, "Optional", availability="free"),
            _event(2, "Meeting", (2026, 10, 21, 10, 30), (2026, 10, 21, 11, 30)),
        ]
        items, warnings = timeline.build_timeline(events, {}, {}, WED)
        assert [i.availability for i in items] == ["free", "blocked"]
        assert warnings == []


class TestOverlapWarnings:
    def test_overlapping_blocked_events_are_reported(self):
        events = [
            _event(1, "A", (2026, 10, 21, 10, 0), (2026, 10, 21, 11, 0)),
            _event(2, "B", (2026, 10, 21, 10, 30), (2026, 10, 21, 11, 30)),
        ]
        items, warnings = timeline.build_timeline(events, {}, {}, WED)
        assert len(items) == 2
        assert warnings == ["Overlap on 2026-10-21: 'A' (10:00-11:00) overlaps 'B' (10:30-11:30)."]

    def test_touching_events_do_not_overlap(self):
        events = [
            _event(1, "A", (2026, 10, 21, 10, 0), (2026, 10, 21, 11, 0)),
            _event(2, "B", (2026, 10, 21, 11, 0), (2026, 10, 21, 12, 0)),
        ]
        assert timeline.build_timeline(events, {}, {}, WED)[1] == []

    def test_travel_overlapping_a_routine_step_is_reported(self):
        routine = SimpleNamespace(steps=[_step(1, "Leave", "start", -40, 30)])
        events = [_event(7, "Class", (2026, 10, 21, 20, 0), (2026, 10, 21, 21, 0), travel_minutes=25, routine_id=3)]

        _, warnings = timeline.build_timeline(events, {3: routine}, {}, WED)

        assert len(warnings) == 1
        assert "'Travel to Class'" in warnings[0] and "'Leave'" in warnings[0]

    def test_zero_duration_steps_never_overlap(self):
        routine = SimpleNamespace(steps=[_step(1, "Reminder", "start", -10, 0)])
        events = [_event(7, "Class", routine_id=3), _event(8, "Other", (2026, 10, 21, 9, 30), (2026, 10, 21, 10, 5))]
        _, warnings = timeline.build_timeline(events, {3: routine}, {}, WED)
        assert len(warnings) == 1 and "Reminder" not in warnings[0]

    def test_free_events_never_overlap(self):
        events = [_event(1, "A", availability="free"), _event(2, "B", availability="free")]
        assert timeline.build_timeline(events, {}, {}, WED)[1] == []


class TestDstTimeline:
    def test_event_on_the_25_hour_day_keeps_the_right_offset_and_travel(self):
        day = date(2026, 10, 25)
        events = [_event(1, "Early class", (2026, 10, 25, 3, 0), (2026, 10, 25, 4, 0), travel_minutes=120)]

        items, _ = timeline.build_timeline(events, {}, {}, day)

        travel_to, event, _travel_home = items
        assert event.start == "2026-10-25T03:00:00+00:00"
        # 120 elapsed minutes before 03:00 WET is 01:00 WET, not 01:00 WEST
        assert travel_to.start == "2026-10-25T01:00:00+00:00"


class TestAllDay:
    def test_all_day_events_listed_for_each_spanned_day(self):
        events = [
            _event(1, "Trip", (2026, 10, 20, 0, 0), (2026, 10, 22, 23, 59), all_day=True),
            _event(2, "Other day", (2026, 10, 25, 0, 0), (2026, 10, 25, 23, 59), all_day=True),
            _event(3, "Timed"),
        ]
        assert [(a.title, a.event_id) for a in timeline.all_day_for_day(events, WED)] == [("Trip", 1)]


class TestWorkAndOffice:
    def test_committed_work_counts_only_tagged_timed_events_of_that_day(self):
        events = [
            _event(1, "Standup", (2026, 10, 21, 10, 0), (2026, 10, 21, 10, 30), tags=["Work"]),
            _event(2, "Client call", (2026, 10, 21, 14, 0), (2026, 10, 21, 15, 0), tags=["work"]),
            _event(3, "Gym", (2026, 10, 21, 18, 0), (2026, 10, 21, 19, 0), tags=["health"]),
            _event(4, "Tomorrow", (2026, 10, 22, 10, 0), (2026, 10, 22, 11, 0), tags=["work"]),
        ]
        assert timeline.committed_work_minutes(events, WED, "work") == 90

    def test_committed_work_uses_elapsed_time_on_the_dst_day(self):
        # 00:00 WEST to 03:00 WET on 2026-10-25 is 4 elapsed hours, not 3
        events = [_event(1, "Night shift", (2026, 10, 25, 0, 0), (2026, 10, 25, 3, 0), tags=["work"])]
        assert timeline.committed_work_minutes(events, date(2026, 10, 25), "work") == 240

    def test_office_days_need_in_person_tagged_events_of_enough_length(self):
        events = [
            _event(1, "Office", (2026, 10, 19, 9, 0), (2026, 10, 19, 17, 0), tags=["office"]),
            _event(2, "Remote office", (2026, 10, 20, 9, 0), (2026, 10, 20, 17, 0), tags=["office"], presence="remote_home"),
            _event(3, "Short visit", (2026, 10, 21, 9, 0), (2026, 10, 21, 9, 30), tags=["office"]),
            _event(4, "Untagged", (2026, 10, 22, 9, 0), (2026, 10, 22, 17, 0)),
            _event(5, "Office again", (2026, 10, 19, 18, 0), (2026, 10, 19, 19, 0), tags=["Office"]),
        ]
        assert timeline.office_days(events, "office", 60) == {date(2026, 10, 19)}
        assert timeline.office_days(events, "office", 0) == {date(2026, 10, 19), date(2026, 10, 21)}

    def test_week_helpers_use_monday_based_weeks(self):
        assert timeline.week_bounds(WED) == (date(2026, 10, 19), date(2026, 10, 25))
        assert timeline.days_left_in_week(WED) == 5
        assert timeline.days_left_in_week(date(2026, 10, 19)) == 7
        assert timeline.days_left_in_week(date(2026, 10, 25)) == 1


class TestRecurringHelpers:
    def test_cadence_classification(self):
        assert not timeline.is_flexible_cadence("FREQ=DAILY")
        assert not timeline.is_flexible_cadence("RRULE:FREQ=WEEKLY;BYDAY=MO,WE")
        assert timeline.is_flexible_cadence("FREQ=WEEKLY")
        assert timeline.is_flexible_cadence("FREQ=MONTHLY")

    def test_due_dates_follow_byday(self):
        days = [date(2026, 10, 19) + timedelta(days=i) for i in range(7)]
        assert timeline.recurring_due_dates("FREQ=WEEKLY;BYDAY=MO,SA", days) == [date(2026, 10, 19), date(2026, 10, 24)]

    def test_daily_is_due_every_day(self):
        days = [WED, WED + timedelta(days=1)]
        assert timeline.recurring_due_dates("FREQ=DAILY", days) == days


class TestRoutineBlocks:
    def test_blocks_show_window_and_fixed_flag(self):
        windows = [
            StepWindow(10, WED, "Shower", 15, time(7, 30), time(9, 0), "home", None, None),
            StepWindow(11, WED, "Lunch", 45, time(13, 0), time(13, 45), None, None, 5),
        ]
        blocks = timeline.routine_blocks_for("Daily", windows, {5: "Lunch list"})
        assert [(b.title, b.window, b.fixed) for b in blocks] == [
            ("Shower", "07:30-09:00", None), ("Lunch", "13:00-13:45", True),
        ]
        assert blocks[1].checklist_note_title == "Lunch list" and blocks[0].routine == "Daily"
