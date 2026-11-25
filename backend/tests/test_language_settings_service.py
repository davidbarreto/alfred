from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.features.language.settings_schemas import LanguageSettingsRead, LanguageSettingsUpdate
from app.features.language.settings_service import LanguageSettingsService

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def service():
    svc = LanguageSettingsService(AsyncMock())
    svc._settings = AsyncMock()
    svc._settings.get_value.return_value = None
    return svc


class TestLanguageSettings:
    async def test_defaults_are_the_old_constants(self, service):
        settings = await service.get()
        assert (settings.requested_retention, settings.leech_threshold, settings.timed_task_seconds) == (0.9, 8, 300)

    async def test_retention_is_read_with_decimals(self, service):
        service._settings.get_value.side_effect = lambda key: "0.85" if key == "language.requested_retention" else None
        assert (await service.get()).requested_retention == 0.85

    async def test_update_stores_only_the_given_fields(self, service):
        await service.update(LanguageSettingsUpdate(leech_threshold=5))
        service._settings.set_value.assert_awaited_once_with("language.leech_threshold", "5")

    @pytest.mark.parametrize("field,value", [("requested_retention", 0.5), ("requested_retention", 0.99), ("leech_threshold", 1)])
    def test_out_of_range(self, field, value):
        with pytest.raises(ValidationError):
            LanguageSettingsUpdate(**{field: value})


class TestRoutes:
    @pytest.fixture
    def client(self):
        from app.dependencies import get_language_settings_service
        from app.main import app

        service = AsyncMock()
        service.get.return_value = LanguageSettingsRead()
        service.update.return_value = LanguageSettingsRead(requested_retention=0.85)
        app.dependency_overrides[get_language_settings_service] = lambda: service
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_get_and_put(self, client):
        assert client.get("/language/settings", headers=AUTH).json()["requested_retention"] == 0.9
        response = client.put("/language/settings", json={"requested_retention": 0.85}, headers=AUTH)
        assert response.status_code == 200 and response.json()["requested_retention"] == 0.85

    def test_out_of_range_is_a_422(self, client):
        assert client.put("/language/settings", json={"requested_retention": 1.5}, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/language/settings").status_code == 403
