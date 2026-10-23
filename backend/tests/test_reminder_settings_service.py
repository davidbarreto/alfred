from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.features.core.reminders.schemas import ReminderSettingsUpdate
from app.features.core.reminders.settings_service import ReminderSettingsService


@pytest.fixture
def service():
    svc = ReminderSettingsService(session=AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    return svc


@pytest.fixture(autouse=True)
def _env_defaults():
    with patch(
        "app.features.core.reminders.settings_service.get_settings",
        return_value=MagicMock(urgency_reset_days=9),
    ):
        yield


class TestGet:
    async def test_returns_defaults_when_nothing_is_stored(self, service):
        result = await service.get()

        assert result.overload_overdue_threshold == 5
        assert result.overload_urgent_threshold == 4
        assert result.overload_max_listed == 5
        assert result.overdue_grace_hours_high == 0
        assert result.overdue_grace_hours_medium == 48
        assert result.overdue_grace_hours_low == 168
        assert result.undated_escalation_days_low == 45
        assert result.catchup_tasks_per_day == 3
        assert result.catchup_stale_days == 30
        assert result.catchup_missed_habit_threshold == 3

    async def test_urgency_reset_days_defaults_to_the_env_value(self, service):
        assert (await service.get()).urgency_reset_days == 9

    async def test_stored_value_overrides_default(self, service):
        async def get_value(key):
            return "12" if key == "reminders.overload_max_listed" else None

        service._settings.get_value.side_effect = get_value

        assert (await service.get()).overload_max_listed == 12

    async def test_stored_zero_is_respected(self, service):
        async def get_value(key):
            return "0" if key == "reminders.overdue_grace_hours_medium" else None

        service._settings.get_value.side_effect = get_value

        assert (await service.get()).overdue_grace_hours_medium == 0


class TestUpdate:
    async def test_stores_only_the_provided_fields(self, service):
        await service.update(ReminderSettingsUpdate(overload_max_listed=8, overdue_grace_hours_low=24))

        stored = {call.args for call in service._settings.set_value.await_args_list}
        assert stored == {("reminders.overload_max_listed", "8"), ("reminders.overdue_grace_hours_low", "24")}

    async def test_zero_is_stored_for_fields_allowing_it(self, service):
        await service.update(ReminderSettingsUpdate(overdue_grace_hours_high=0))

        service._settings.set_value.assert_awaited_once_with("reminders.overdue_grace_hours_high", "0")

    async def test_empty_update_stores_nothing(self, service):
        await service.update(ReminderSettingsUpdate())

        service._settings.set_value.assert_not_awaited()

    @pytest.mark.parametrize(
        "field,value",
        [("overload_max_listed", 0), ("overload_urgent_threshold", 0), ("overload_urgent_interval_hours", 25),
         ("undated_escalation_days_low", 0), ("overdue_grace_hours_low", -1),
         ("catchup_tasks_per_day", 0), ("catchup_stale_days", 6), ("catchup_missed_habit_threshold", 8)],
    )
    def test_rejects_out_of_range(self, field, value):
        with pytest.raises(ValidationError):
            ReminderSettingsUpdate(**{field: value})
