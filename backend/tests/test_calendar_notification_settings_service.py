import json

import pytest
from unittest.mock import AsyncMock

from app.features.organizer.calendar_events.notification_settings.schemas import (
    CalendarNotificationCascadeUpdate,
)
from app.features.organizer.calendar_events.notification_settings.service import (
    CASCADES_KEY,
    DEFAULT_CASCADES,
    CalendarNotificationSettingsService,
)


@pytest.fixture
def service():
    svc = CalendarNotificationSettingsService.__new__(CalendarNotificationSettingsService)
    svc._settings = AsyncMock()
    return svc


class TestGet:
    async def test_returns_defaults_when_unset(self, service):
        service._settings.get_value.return_value = None
        result = await service.get()
        service._settings.get_value.assert_called_once_with(CASCADES_KEY)
        assert result.profiles == DEFAULT_CASCADES

    async def test_merges_stored_overrides_over_defaults(self, service):
        service._settings.get_value.return_value = json.dumps({"light": ["10m", "0"]})
        result = await service.get()
        assert result.profiles["light"] == ["10m", "0"]
        assert result.profiles["cant_miss"] == DEFAULT_CASCADES["cant_miss"]


class TestGetCascade:
    async def test_returns_profile_cascade(self, service):
        service._settings.get_value.return_value = None
        result = await service.get_cascade("aware")
        assert result == DEFAULT_CASCADES["aware"]

    async def test_unknown_profile_falls_back_to_normal(self, service):
        service._settings.get_value.return_value = None
        result = await service.get_cascade("bogus")
        assert result == DEFAULT_CASCADES["normal"]


class TestUpdateProfile:
    async def test_stores_merged_profiles_as_json(self, service):
        service._settings.get_value.return_value = None
        await service.update_profile("light", CalendarNotificationCascadeUpdate(offsets=["10m", "0"]))
        stored_key, stored_value = service._settings.set_value.call_args.args
        assert stored_key == CASCADES_KEY
        stored = json.loads(stored_value)
        assert stored["light"] == ["10m", "0"]
        assert stored["cant_miss"] == DEFAULT_CASCADES["cant_miss"]

    async def test_rejects_invalid_offset(self, service):
        service._settings.get_value.return_value = None
        with pytest.raises(Exception):
            await service.update_profile("light", CalendarNotificationCascadeUpdate(offsets=["nonsense"]))
