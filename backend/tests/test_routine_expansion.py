from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.features.organizer.routines.expansion import (
    expand_event_steps,
    expand_scheduled_steps,
    localize,
    scheduled_dates,
    shift_minutes,
)

LISBON = ZoneInfo("Europe/Lisbon")


def _step(id=1, title="Step", duration=0, anchor=None, offset=None, window=None, **extra):
    window_start, window_end = window if window else (None, None)
    return SimpleNamespace(
        id=id, title=title, duration_minutes=duration, anchor=anchor, offset_minutes=offset,
        window_start=window_start, window_end=window_end, context=extra.get("context"),
        location=extra.get("location"), checklist_note_id=extra.get("note"),
    )


class TestEventRelativeSteps:
    # Wednesday 2026-10-21, evening class 20:00-21:00 (Lisbon, UTC+1)
    start = datetime(2026, 10, 21, 20, 0, tzinfo=LISBON)
    end = datetime(2026, 10, 21, 21, 0, tzinfo=LISBON)

    def test_steps_land_at_anchor_plus_offset(self):
        steps = [
            _step(1, "Prepare dinner", duration=40, anchor="start", offset=-120, context="home", note=26),
            _step(2, "Leave to pick up", duration=20, anchor="start", offset=-50, context="out", location="Course"),
            _step(3, "Stretch at home", duration=15, anchor="end", offset=25),
        ]

        result = expand_event_steps(steps, self.start, self.end)

        assert [(o.step_id, o.start.strftime("%H:%M"), o.end.strftime("%H:%M")) for o in result] == [
            (1, "18:00", "18:40"),
            (2, "19:10", "19:30"),
            (3, "21:25", "21:40"),
        ]
        assert result[0].checklist_note_id == 26
        assert result[1].location == "Course"
        assert result[0].start.utcoffset() == timedelta(hours=1)

    def test_results_are_sorted_by_start(self):
        steps = [_step(1, anchor="end", offset=10), _step(2, anchor="start", offset=-30)]
        assert [o.step_id for o in expand_event_steps(steps, self.start, self.end)] == [2, 1]

    def test_window_form_steps_are_ignored(self):
        steps = [_step(1, window=(time(7, 30), time(9, 0)), duration=15)]
        assert expand_event_steps(steps, self.start, self.end) == []

    def test_zero_duration_step_is_a_point(self):
        occurrence = expand_event_steps([_step(1, anchor="start", offset=-10)], self.start, self.end)[0]
        assert occurrence.start == occurrence.end

    def test_offsets_use_elapsed_time_across_the_autumn_dst_change(self):
        # 2026-10-25 is 25 hours long in Lisbon (clocks go back at 02:00 WEST), so 120 minutes
        # before 03:00 WET is 01:00 WET, not the earlier 01:00 WEST that wall-clock subtraction gives.
        event_start = datetime(2026, 10, 25, 3, 0, tzinfo=LISBON)
        occurrence = expand_event_steps([_step(1, anchor="start", offset=-120)], event_start, event_start)[0]

        assert occurrence.start.astimezone(timezone.utc) == datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
        assert occurrence.start.utcoffset() == timedelta(0)

    def test_offsets_use_elapsed_time_across_the_spring_dst_change(self):
        # 2026-03-29: clocks jump 01:00 -> 02:00, so 120 minutes before 03:00 is 00:00 the same day.
        event_start = datetime(2026, 3, 29, 3, 0, tzinfo=LISBON)
        occurrence = expand_event_steps([_step(1, anchor="start", offset=-120)], event_start, event_start)[0]

        assert occurrence.start.astimezone(timezone.utc) == datetime(2026, 3, 29, 0, 0, tzinfo=timezone.utc)


class TestHelpers:
    def test_localize_attaches_the_configured_zone(self):
        assert localize(datetime(2026, 10, 21, 10, 0)).utcoffset() == timedelta(hours=1)

    def test_localize_keeps_aware_values(self):
        aware = datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
        assert localize(aware) is aware

    def test_shift_minutes_goes_through_utc(self):
        before = datetime(2026, 10, 25, 0, 30, tzinfo=LISBON)  # WEST
        assert shift_minutes(before, 120).astimezone(timezone.utc) == datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)


class TestScheduledDates:
    def test_daily_rule_covers_the_requested_range(self):
        days = scheduled_dates("FREQ=DAILY", date(2026, 10, 1), date(2026, 10, 21), date(2026, 10, 23))
        assert days == [date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23)]

    def test_weekly_byday_rule(self):
        days = scheduled_dates("FREQ=WEEKLY;BYDAY=MO,WE", date(2026, 10, 1), date(2026, 10, 19), date(2026, 10, 25))
        assert days == [date(2026, 10, 19), date(2026, 10, 21)]

    def test_rrule_prefix_is_accepted(self):
        days = scheduled_dates("RRULE:FREQ=DAILY", date(2026, 10, 1), date(2026, 10, 21), date(2026, 10, 21))
        assert days == [date(2026, 10, 21)]

    def test_nothing_before_starts_on(self):
        days = scheduled_dates("FREQ=DAILY", date(2026, 10, 22), date(2026, 10, 20), date(2026, 10, 23))
        assert days == [date(2026, 10, 22), date(2026, 10, 23)]

    def test_count_is_honoured(self):
        days = scheduled_dates("FREQ=DAILY;COUNT=2", date(2026, 10, 20), date(2026, 10, 20), date(2026, 10, 31))
        assert days == [date(2026, 10, 20), date(2026, 10, 21)]

    def test_until_is_honoured(self):
        days = scheduled_dates("FREQ=DAILY;UNTIL=20261022", date(2026, 10, 20), date(2026, 10, 20), date(2026, 10, 31))
        assert days == [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]

    def test_invalid_rule_raises(self):
        with pytest.raises(ValueError):
            scheduled_dates("FREQ=SOMETIMES", date(2026, 10, 1), date(2026, 10, 1), date(2026, 10, 2))


class TestScheduledSteps:
    steps = [
        _step(10, "Shower", duration=15, window=(time(7, 30), time(9, 0)), context="home"),
        _step(11, "Lunch", duration=45, window=(time(13, 0), time(13, 45))),
        _step(12, "Ignored relative step", anchor="start", offset=-10),
    ]

    def test_one_window_per_window_step_per_day(self):
        windows = expand_scheduled_steps(self.steps, [date(2026, 10, 21), date(2026, 10, 22)])
        assert [(w.day.isoformat(), w.step_id) for w in windows] == [
            ("2026-10-21", 10), ("2026-10-21", 11), ("2026-10-22", 10), ("2026-10-22", 11),
        ]

    def test_flexible_window_is_not_fixed(self):
        windows = expand_scheduled_steps(self.steps, [date(2026, 10, 21)])
        shower, lunch = windows
        assert shower.fixed is False
        assert (shower.window_start, shower.window_end, shower.duration_minutes) == (time(7, 30), time(9, 0), 15)
        assert shower.context == "home"

    def test_window_as_long_as_the_duration_is_a_fixed_time(self):
        lunch = expand_scheduled_steps(self.steps, [date(2026, 10, 21)])[1]
        assert lunch.fixed is True

    def test_no_days_no_windows(self):
        assert expand_scheduled_steps(self.steps, []) == []
