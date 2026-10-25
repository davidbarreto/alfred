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


class TestGet:
    async def test_defaults(self, plans, settings):
        result = await handle_day_plan("get", {}, plans, settings)
        plans.get_plan.assert_awaited_once_with(None, 1, None)
        assert result["date"] == "2026-10-21"

    async def test_arguments_are_parsed(self, plans, settings):
        await handle_day_plan("get", {"date": "2026-10-26", "days": "7", "work_minutes": "0"}, plans, settings)
        plans.get_plan.assert_awaited_once_with(date(2026, 10, 26), 7, 0)

    async def test_null_fields_are_omitted_from_the_output(self, plans, settings):
        result = await handle_day_plan("get", {}, plans, settings)
        assert "timeline" not in result and "study" not in result and "office" not in result

    @pytest.mark.parametrize("args", [{"days": "0"}, {"days": "8"}, {"days": "x"}, {"date": "tomorrow"}, {"work_minutes": "-1"}, {"work_minutes": "2000"}])
    async def test_bad_arguments_are_400(self, plans, settings, args):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("get", args, plans, settings)
        assert exc.value.status_code == 400
        plans.get_plan.assert_not_called()


class TestSettings:
    async def test_show(self, plans, settings):
        result = await handle_day_plan("settings", {}, plans, settings)
        assert result["work_target_minutes"] == 480

    async def test_set_parses_every_field(self, plans, settings):
        await handle_day_plan(
            "set_settings",
            {"wake_time": "07:30", "work_target_minutes": "420", "preferred_work_windows": "10:00-14:00, 16:00-18:00",
             "office_days_per_week": "4", "office_min_minutes": "60", "work_tag": "job", "office_tag": "hq", "sleep_time": "23:30"},
            plans, settings,
        )
        update = settings.update.call_args.args[0]
        assert update == PlanningSettingsUpdate(
            wake_time="07:30", sleep_time="23:30", work_target_minutes=420,
            preferred_work_windows=["10:00-14:00", "16:00-18:00"], office_days_per_week=4,
            office_min_minutes=60, work_tag="job", office_tag="hq",
        )

    async def test_empty_value_resets_a_setting(self, plans, settings):
        await handle_day_plan("set_settings", {"office_days_per_week": "", "wake_time": "", "preferred_work_windows": ""}, plans, settings)
        update = settings.update.call_args.args[0]
        assert update.model_dump(exclude_unset=True) == {
            "office_days_per_week": None, "wake_time": None, "preferred_work_windows": None,
        }

    async def test_nothing_to_set_is_400(self, plans, settings):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("set_settings", {}, plans, settings)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("args", [{"wake_time": "7am"}, {"office_days_per_week": "9"}, {"preferred_work_windows": "late"}, {"work_target_minutes": "lots"}])
    async def test_invalid_settings_are_400(self, plans, settings, args):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("set_settings", args, plans, settings)
        assert exc.value.status_code == 400

    async def test_unknown_command_is_400(self, plans, settings):
        with pytest.raises(HTTPException) as exc:
            await handle_day_plan("explode", {}, plans, settings)
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
