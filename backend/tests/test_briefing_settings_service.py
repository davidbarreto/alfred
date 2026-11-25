from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.briefing.settings_schemas import BriefingSettingsRead, BriefingSettingsUpdate
from app.features.briefing.settings_service import BriefingSettingsService

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def service():
    svc = BriefingSettingsService(AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    return svc


class TestBriefingSettings:
    async def test_defaults_are_the_constants_the_briefing_used(self, service):
        settings = await service.get()
        assert (settings.lookahead_days, settings.holiday_lookahead_days) == (3, 7)
        assert (settings.max_tasks_today, settings.max_tasks_upcoming, settings.max_events_today,
                settings.max_events_upcoming, settings.max_shopping_items, settings.max_recurring_items) == (8, 4, 8, 4, 6, 5)

    async def test_stored_values_win_and_blank_is_the_default(self, service):
        stored = {"briefing.lookahead_days": "5", "briefing.max_tasks_today": ""}
        service._settings.get_value.side_effect = lambda key: stored.get(key)
        settings = await service.get()
        assert (settings.lookahead_days, settings.max_tasks_today) == (5, 8)

    async def test_update_stores_only_the_given_fields(self, service):
        await service.update(BriefingSettingsUpdate(holiday_lookahead_days=14, max_events_today=None))
        service._settings.set_value.assert_awaited_once_with("briefing.holiday_lookahead_days", "14")

    @pytest.mark.parametrize("field,value", [("lookahead_days", 0), ("lookahead_days", 15), ("max_tasks_today", 0)])
    def test_out_of_range(self, field, value):
        with pytest.raises(ValidationError):
            BriefingSettingsUpdate(**{field: value})


class TestRoutes:
    @pytest.fixture
    def client(self):
        from app.dependencies import get_briefing_settings_service
        from app.main import app

        service = AsyncMock()
        service.get.return_value = BriefingSettingsRead()
        service.update.return_value = BriefingSettingsRead(lookahead_days=5)
        app.dependency_overrides[get_briefing_settings_service] = lambda: service
        yield TestClient(app), service
        app.dependency_overrides.clear()

    def test_get_and_put(self, client):
        test_client, service = client
        assert test_client.get("/briefing/settings", headers=AUTH).json()["lookahead_days"] == 3
        response = test_client.put("/briefing/settings", json={"lookahead_days": 5}, headers=AUTH)
        assert response.status_code == 200 and response.json()["lookahead_days"] == 5
        assert service.update.await_args.args[0].model_dump(exclude_unset=True) == {"lookahead_days": 5}

    def test_out_of_range_is_a_422(self, client):
        test_client, _ = client
        assert test_client.put("/briefing/settings", json={"lookahead_days": 99}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        test_client, _ = client
        assert test_client.get("/briefing/settings").status_code == 403
