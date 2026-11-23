from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.assistant_settings.schemas import AssistantSettingsRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get.return_value = AssistantSettingsRead(user_name="Sam", persona_additions=None, base_persona="# Alfred")
    svc.update.return_value = AssistantSettingsRead(user_name="Sam", persona_additions="Likes jazz.", base_persona="# Alfred")
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_assistant_settings_service
    app.dependency_overrides[get_assistant_settings_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestAssistantSettingsRoutes:
    def test_get(self, client):
        response = client.get("/core/assistant-settings", headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {"user_name": "Sam", "persona_additions": None, "base_persona": "# Alfred"}

    def test_put_passes_only_given_fields(self, client, mock_service):
        response = client.put("/core/assistant-settings", headers=AUTH, json={"persona_additions": "Likes jazz."})

        assert response.status_code == 200
        assert mock_service.update.call_args.args[0].model_dump(exclude_unset=True) == {"persona_additions": "Likes jazz."}

    def test_too_long_name_is_422(self, client):
        assert client.put("/core/assistant-settings", headers=AUTH, json={"user_name": "x" * 51}).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/core/assistant-settings").status_code == 403
