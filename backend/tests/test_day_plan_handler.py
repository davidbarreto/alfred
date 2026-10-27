from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.day_plan import handle_day_plan
from app.assistant.commands.registry import COMMAND_DEFINITIONS
from app.features.planning.schemas import DayPlanRead, PlanningSettingsRead, PlanningSettingsUpdate
from app.features.planning.settings_service import PlanningSettingsService


def _plan() -> DayPlanRead:
    return DayPlanRead(date="2026-10-21", timezone="Europe/Lisbon", preferences={"work_target_minutes": 480})


@pytest.fixture
def plans():
    svc = AsyncMock()
    svc.get_plan.return_value = _plan()
    return svc


@pytest.fixture
def settings():
    svc = AsyncMock()
    stored = PlanningSettingsRead(work_target_minutes=480, work_tag="work", office_tag="office")
    svc.get.return_value = stored
    svc.update.return_value = stored
    return svc


@pytest.fixture
def saved():
    svc = AsyncMock()
    svc.save.return_value = []
    svc.get_saved.return_value = []
    svc.get_history.return_value = []
    return svc


class TestGet:
    async def test_defaults(self, plans, settings, saved):
        result = await handle_day_plan("get", {}, plans, settings, saved)
        plans.get_plan.assert_awaited_once_with(None, 1, None)
        assert result["date"] == "2026-10-21"

    async def test_arguments_are_parsed(self, plans, settings, saved):
        await handle_day_plan("get", {"date": "2026-10-26", "days": "7", "work_minutes": "0"}, plans, settings, saved)
        plans.get_plan.assert_awaited_once_with(date(2026, 10, 26), 7, 0)

    async def test_null_fields_are_omitted_from_the_output(self, plans, settings, saved):
        result = await handle_day_plan("get", {}, plans, settings, saved)
        assert "timeline" not in result and "study" not in result and "office" not in result

    @pytest.mark.parametrize("args", [{"days": "0"}, {"days": "8"}, {"days": "x"}, {"date": "tomorrow"}, {"work_minutes": "-1"}, {"work_minutes": "2000"}])
    async def test_bad_arguments_are_400(self, plans, settings, saved, args):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("get", args, plans, settings, saved)
        assert exc.value.status_code == 400
        plans.get_plan.assert_not_called()


class TestSettings:
    async def test_show(self, plans, settings, saved):
        result = await handle_day_plan("settings", {}, plans, settings, saved)
        assert result["work_target_minutes"] == 480

    async def test_set_parses_every_field(self, plans, settings, saved):
        await handle_day_plan(
            "set_settings",
            {"wake_time": "07:30", "work_target_minutes": "420", "preferred_work_windows": "10:00-14:00, 16:00-18:00",
             "office_days_per_week": "4", "office_min_minutes": "60", "work_tag": "job", "office_tag": "hq", "sleep_time": "23:30"},
            plans, settings, saved,
        )
        update = settings.update.call_args.args[0]
        assert update == PlanningSettingsUpdate(
            wake_time="07:30", sleep_time="23:30", work_target_minutes=420,
            preferred_work_windows=["10:00-14:00", "16:00-18:00"], office_days_per_week=4,
            office_min_minutes=60, work_tag="job", office_tag="hq",
        )

    async def test_workdays_are_parsed_from_a_comma_list(self, plans, settings, saved):
        await handle_day_plan("set_settings", {"workdays": "Mon, tue,sat"}, plans, settings, saved)
        assert settings.update.call_args.args[0] == PlanningSettingsUpdate(workdays=["mon", "tue", "sat"])

    async def test_empty_value_resets_a_setting(self, plans, settings, saved):
        await handle_day_plan("set_settings", {"office_days_per_week": "", "wake_time": "", "preferred_work_windows": ""}, plans, settings, saved)
        update = settings.update.call_args.args[0]
        assert update.model_dump(exclude_unset=True) == {
            "office_days_per_week": None, "wake_time": None, "preferred_work_windows": None,
        }

    async def test_nothing_to_set_is_400(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("set_settings", {}, plans, settings, saved)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("args", [{"wake_time": "7am"}, {"office_days_per_week": "9"}, {"preferred_work_windows": "late"}, {"work_target_minutes": "lots"}])
    async def test_invalid_settings_are_400(self, plans, settings, saved, args):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("set_settings", args, plans, settings, saved)
        assert exc.value.status_code == 400

    async def test_unknown_command_is_400(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("explode", {}, plans, settings, saved)
        assert exc.value.status_code == 400


class TestRegistry:
    def test_actions(self):
        assert set(COMMAND_DEFINITIONS["day_plan"]) >= {"get", "settings", "set_settings"}

    def test_get_details_explain_every_section_and_the_workflow_limits(self):
        details = COMMAND_DEFINITIONS["day_plan"]["get"]["details"]
        for phrase in (
            "timeline", "routine_blocks", "all_day", "work", "preferences", "overdue_tasks", "due_tasks",
            "recurring_tasks", "backlog_tasks", "study", "shopping", "office", "warnings", "days=1",
            "free slots are not returned", "never schedules or notifies", "work_minutes", "UTC offset",
            "light/aware", "important/cant_miss", "fixed=true", "flexible=true",
        ):
            assert phrase in details, phrase

    def test_settings_details_list_every_setting_with_units(self):
        details = COMMAND_DEFINITIONS["day_plan"]["set_settings"]["details"]
        for phrase in ("HH:MM", "work_target_minutes", "minutes", "preferred_work_windows", "work_tag", "office_tag",
                       "office_days_per_week", "office_min_minutes"):
            assert phrase in details

    def test_settings_flags_cover_every_field(self):
        keys = set(COMMAND_DEFINITIONS["day_plan"]["set_settings"]["flags"].values())
        assert keys == set(PlanningSettingsRead.model_fields)


class TestSaveCommand:
    _DAYS = (
        '[{"date": "2026-10-21", "notes": "Light day", "items": [{"start": "2026-10-21T09:00:00+01:00", '
        '"end": "2026-10-21T10:00:00+01:00", "kind": "task", "ref_id": 4, "title": "Write"}]}]'
    )

    async def test_days_json_string_is_parsed_and_saved(self, plans, settings, saved):
        await handle_day_plan("save", {"days": self._DAYS}, plans, settings, saved)

        payload, source = saved.save.call_args.args
        assert payload.days[0].date == date(2026, 10, 21)
        assert payload.days[0].items[0].ref_id == 4 and payload.days[0].notes == "Light day"
        assert source == "mcp"

    async def test_portal_source_is_recorded(self, plans, settings, saved):
        await handle_day_plan("save", {"days": self._DAYS}, plans, settings, saved, source="web")
        assert saved.save.call_args.args[1] == "portal"

    async def test_a_list_is_accepted_too(self, plans, settings, saved):
        import json

        await handle_day_plan("save", {"days": json.loads(self._DAYS)}, plans, settings, saved)
        saved.save.assert_awaited_once()

    @pytest.mark.parametrize("days", ["not json", '{"date": "2026-10-21"}', "[]", '[{"date": "x", "items": []}]'])
    async def test_invalid_days_are_400(self, plans, settings, saved, days):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("save", {"days": days}, plans, settings, saved)
        assert exc.value.status_code == 400
        saved.save.assert_not_called()

    async def test_json_error_message_points_at_the_problem(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("save", {"days": "[{"}, plans, settings, saved)
        assert "valid JSON" in exc.value.detail and "column" in exc.value.detail

    async def test_naive_datetime_is_a_400_naming_the_offset(self, plans, settings, saved):
        days = self._DAYS.replace("+01:00", "")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("save", {"days": days}, plans, settings, saved)
        assert exc.value.status_code == 400 and "UTC offset" in exc.value.detail

    async def test_validation_errors_from_the_service_are_422(self, plans, settings, saved):
        from app.features.planning.saved_plans.service import SavedPlanValidationError

        saved.save.side_effect = SavedPlanValidationError("Unknown task ref_id(s): 999")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("save", {"days": self._DAYS}, plans, settings, saved)
        assert exc.value.status_code == 422 and "999" in exc.value.detail

    async def test_conflicts_are_409(self, plans, settings, saved):
        from app.features.planning.saved_plans.service import SavedPlanConflictError

        saved.save.side_effect = SavedPlanConflictError("race")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("save", {"days": self._DAYS}, plans, settings, saved)
        assert exc.value.status_code == 409


class TestLoadCommands:
    async def test_get_saved_range_and_version(self, plans, settings, saved):
        await handle_day_plan("get_saved", {"from": "2026-10-19", "to": "2026-10-25", "version": "1"}, plans, settings, saved)
        saved.get_saved.assert_awaited_once_with(date(2026, 10, 19), date(2026, 10, 25), 1)

    async def test_to_defaults_to_from(self, plans, settings, saved):
        await handle_day_plan("get_saved", {"from": "2026-10-19"}, plans, settings, saved)
        saved.get_saved.assert_awaited_once_with(date(2026, 10, 19), date(2026, 10, 19), None)

    async def test_from_is_required(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("get_saved", {}, plans, settings, saved)
        assert exc.value.status_code == 400

    async def test_range_errors_are_422(self, plans, settings, saved):
        from app.features.planning.saved_plans.service import SavedPlanValidationError

        saved.get_saved.side_effect = SavedPlanValidationError("too long")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("get_saved", {"from": "2026-01-01", "to": "2026-12-31"}, plans, settings, saved)
        assert exc.value.status_code == 422

    async def test_history(self, plans, settings, saved):
        await handle_day_plan("history", {"date": "2026-10-21"}, plans, settings, saved)
        saved.get_history.assert_awaited_once_with(date(2026, 10, 21))

    async def test_history_needs_a_date(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("history", {}, plans, settings, saved)
        assert exc.value.status_code == 400


class TestMiss:
    async def test_miss_by_ref_id_defaults_to_a_task(self, plans, settings, saved):
        saved.set_missed_on.return_value = _saved_read()
        await handle_day_plan("miss", {"date": "2026-10-21", "ref_id": "4"}, plans, settings, saved)
        saved.set_missed_on.assert_awaited_once_with(
            date(2026, 10, 21), True, kind="task", ref_id=4, title=None, start=None
        )

    async def test_unmiss_by_title_and_start(self, plans, settings, saved):
        saved.set_missed_on.return_value = _saved_read()
        await handle_day_plan(
            "unmiss", {"date": "2026-10-21", "title": "metro", "kind": "transport", "start": "08:00"}, plans, settings, saved
        )
        saved.set_missed_on.assert_awaited_once_with(
            date(2026, 10, 21), False, kind="transport", ref_id=None, title="metro", start="08:00"
        )

    async def test_needs_a_date(self, plans, settings, saved):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("miss", {"ref_id": "4"}, plans, settings, saved)
        assert exc.value.status_code == 400

    async def test_no_matching_block_is_404_and_ambiguity_422(self, plans, settings, saved):
        from app.features.planning.saved_plans.service import SavedPlanNotFoundError, SavedPlanValidationError

        saved.set_missed_on.side_effect = SavedPlanNotFoundError("none")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("miss", {"date": "2026-10-21", "ref_id": "4"}, plans, settings, saved)
        assert exc.value.status_code == 404
        saved.set_missed_on.side_effect = SavedPlanValidationError("2 blocks match")
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("miss", {"date": "2026-10-21", "ref_id": "4"}, plans, settings, saved)
        assert exc.value.status_code == 422

    def test_details_tell_the_llm_when_to_use_it(self):
        details = COMMAND_DEFINITIONS["day_plan"]["miss"]["details"]
        for phrase in ("did not do", "missed=true", "no new version", "ref_id", "stays open"):
            assert phrase in details.replace("creates no new version", "no new version"), phrase
        assert COMMAND_DEFINITIONS["day_plan"]["unmiss"]["arg_keys"] == ["date"]

    def test_save_details_describe_work_transport_and_missed_blocks(self):
        details = COMMAND_DEFINITIONS["day_plan"]["save"]["details"]
        for phrase in ("work/transport", "travel_minutes", "missed=true", "Free-form kinds take no ref_id"):
            assert phrase in details, phrase

    def test_save_details_say_eating_is_a_meal_not_a_break(self):
        details = COMMAND_DEFINITIONS["day_plan"]["save"]["details"]
        for phrase in ("breakfast, lunch, dinner", "kind meal, never break", "pause to rest"):
            assert phrase in details, phrase


def _saved_read():
    from datetime import datetime, timezone

    from app.features.planning.saved_plans.schemas import SavedDayPlanRead

    now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
    return SavedDayPlanRead(
        id=1, plan_date=date(2026, 10, 21), version=1, items=[], source="mcp", created_at=now, updated_at=now
    )


class TestSaveRegistry:
    def test_actions_exist(self):
        assert {"save", "get_saved", "history"} <= set(COMMAND_DEFINITIONS["day_plan"])

    def test_save_details_document_the_json_shape_and_ref_kinds(self):
        details = COMMAND_DEFINITIONS["day_plan"]["save"]["details"]
        for phrase in (
            "JSON", "UTC offset", "event", "task", "study_item", "activity", "routine_step", "routine_block",
            "meal", "break", "other", "ref_id", "notes", "Only the dates in the call get a new version", "get_saved",
        ):
            assert phrase in details, phrase

    def test_save_requires_days(self):
        config = COMMAND_DEFINITIONS["day_plan"]["save"]
        assert config["requires_args"] and config["arg_keys"] == ["days"]
