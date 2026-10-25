import pytest

from scripts.backfill_task_planning_fields import (
    TagRename,
    parse_duration_tag,
    plan_area_renames,
    plan_task_change,
)


class TestParseDurationTag:
    @pytest.mark.parametrize("tag,minutes", [
        ("30m", 30), ("45min", 45), ("2h", 120), ("1.5h", 90), ("1hr", 60), ("0.5h", 30),
        ("1h30m", 90), ("2h15", 135), ("2H", 120), (" 30m ", 30),
    ])
    def test_recognised_forms(self, tag, minutes):
        assert parse_duration_tag(tag) == minutes

    @pytest.mark.parametrize("tag", ["work", "context:phone", "m", "h", "30", "30 minutes", "0m", "0h", "1.2.3h", "abc30m", "30mx"])
    def test_everything_else_is_not_a_duration(self, tag):
        assert parse_duration_tag(tag) is None


class TestPlanTaskChange:
    def test_context_and_duration_tags_become_fields(self):
        change = plan_task_change(1, "Buy tickets", ["context:phone", "10m", "admin"], None, None)
        assert (change.estimate_minutes, change.context, change.notes) == (10, "phone", [])
        assert change.sets_anything

    def test_context_value_is_case_insensitive(self):
        assert plan_task_change(1, "x", ["Context:Home"], None, None).context == "home"

    def test_task_without_hints_changes_nothing(self):
        change = plan_task_change(1, "x", ["work", "area:work"], None, None)
        assert not change.sets_anything and change.notes == []

    def test_unknown_context_is_reported_not_applied(self):
        change = plan_task_change(1, "x", ["context:office"], None, None)
        assert change.context is None and "unknown context 'office'" in change.notes[0]

    def test_unknown_context_does_not_block_a_valid_one(self):
        change = plan_task_change(1, "x", ["context:office", "context:out"], None, None)
        assert change.context == "out" and len(change.notes) == 1

    def test_conflicting_contexts_are_left_alone(self):
        change = plan_task_change(1, "x", ["context:home", "context:phone"], None, None)
        assert change.context is None and "conflicting contexts" in change.notes[0]

    def test_conflicting_durations_are_left_alone(self):
        change = plan_task_change(1, "x", ["30m", "2h"], None, None)
        assert change.estimate_minutes is None and "conflicting duration tags [30, 120]" in change.notes[0]

    def test_same_duration_written_twice_is_not_a_conflict(self):
        assert plan_task_change(1, "x", ["60m", "1h"], None, None).estimate_minutes == 60

    def test_existing_values_are_never_overwritten(self):
        change = plan_task_change(1, "x", ["context:phone", "30m"], 45, "home")
        assert not change.sets_anything
        assert any("already set to 'home'" in n for n in change.notes)
        assert any("already set to 45" in n for n in change.notes)

    def test_one_field_can_be_filled_while_the_other_is_kept(self):
        change = plan_task_change(1, "x", ["context:phone", "30m"], 45, None)
        assert (change.context, change.estimate_minutes) == ("phone", None)


class TestPlanAreaRenames:
    def test_area_tags_become_plain_names(self):
        renames, skipped = plan_area_renames({"notion": ["area:work", "area:home", "errands"]})
        assert renames == [TagRename("notion", "area:home", "home"), TagRename("notion", "area:work", "work")]
        assert skipped == []

    def test_collision_with_an_existing_tag_is_skipped(self):
        renames, skipped = plan_area_renames({"notion": ["area:work", "Work"]})
        assert renames == [] and "collide" in skipped[0]

    def test_two_tags_that_would_become_the_same_name_only_rename_one(self):
        renames, skipped = plan_area_renames({"notion": ["area:work", "AREA:WORK"]})
        assert len(renames) == 1 and len(skipped) == 1

    def test_providers_are_independent(self):
        renames, _ = plan_area_renames({"a": ["area:work"], "b": ["area:work", "work"]})
        assert renames == [TagRename("a", "area:work", "work")]

    def test_empty_name_after_the_prefix_is_skipped(self):
        renames, skipped = plan_area_renames({"a": ["area:", "area:  "]})
        assert renames == [] and len(skipped) == 2

    def test_non_area_tags_are_untouched(self):
        assert plan_area_renames({"a": ["work", "context:phone"]}) == ([], [])
