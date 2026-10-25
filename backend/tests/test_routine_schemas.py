from datetime import date, time

import pytest
from pydantic import ValidationError

from app.features.organizer.routines.schemas import (
    RoutineCreate,
    RoutineStepBase,
    RoutineStepCreate,
    RoutineUpdate,
)


class TestStepTimingForm:
    def test_relative_form(self):
        step = RoutineStepBase(title="Leave", anchor="start", offset_minutes=-50, duration_minutes=20)
        assert (step.anchor, step.offset_minutes) == ("start", -50)

    def test_window_form(self):
        step = RoutineStepBase(title="Shower", window_start=time(7, 30), window_end=time(9, 0), duration_minutes=15)
        assert step.window_end == time(9, 0)

    def test_window_accepts_hh_mm_strings(self):
        step = RoutineStepBase(title="Lunch", window_start="13:00", window_end="13:45")
        assert step.window_start == time(13, 0)

    def test_duration_defaults_to_zero(self):
        assert RoutineStepBase(title="x", anchor="end", offset_minutes=0).duration_minutes == 0

    @pytest.mark.parametrize(
        "fields",
        [
            {},
            {"anchor": "start"},
            {"offset_minutes": 5},
            {"window_start": "07:00"},
            {"anchor": "start", "offset_minutes": 5, "window_start": "07:00", "window_end": "08:00"},
            {"window_start": "09:00", "window_end": "09:00"},
            {"window_start": "10:00", "window_end": "09:00"},
            {"anchor": "middle", "offset_minutes": 0},
            {"anchor": "start", "offset_minutes": 0, "context": "office"},
            {"anchor": "start", "offset_minutes": 0, "duration_minutes": -1},
        ],
    )
    def test_invalid_combinations_rejected(self, fields):
        with pytest.raises(ValidationError):
            RoutineStepBase(title="x", **fields)

    def test_create_adds_optional_position(self):
        step = RoutineStepCreate(title="x", anchor="start", offset_minutes=0, position=2)
        assert step.position == 2


class TestRoutine:
    def test_event_based_routine_needs_no_rule(self):
        assert RoutineCreate(name="Dinner").recurrence_rule is None

    def test_scheduled_routine_needs_rule_and_start_date(self):
        routine = RoutineCreate(name="Morning", recurrence_rule="FREQ=DAILY", starts_on=date(2026, 10, 1))
        assert routine.active is True

    @pytest.mark.parametrize("fields", [{"recurrence_rule": "FREQ=DAILY"}, {"starts_on": date(2026, 10, 1)}])
    def test_rule_and_start_date_go_together(self, fields):
        with pytest.raises(ValidationError):
            RoutineCreate(name="x", **fields)

    @pytest.mark.parametrize("field", ["name", "active"])
    def test_required_columns_cannot_be_cleared(self, field):
        with pytest.raises(ValidationError):
            RoutineUpdate(**{field: None})

    def test_rule_can_be_cleared_on_update(self):
        update = RoutineUpdate(recurrence_rule=None, starts_on=None)
        assert update.model_dump(exclude_unset=True) == {"recurrence_rule": None, "starts_on": None}
