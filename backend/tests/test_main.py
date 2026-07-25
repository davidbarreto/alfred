from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.google_oauth.client import GoogleTokenExpiredError

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_contact_service():
    svc = AsyncMock()
    svc.sync.side_effect = GoogleTokenExpiredError("google_contacts")
    return svc


@pytest.fixture
def client(mock_contact_service):
    from app.main import app
    from app.dependencies import get_contact_service
    app.dependency_overrides[get_contact_service] = lambda: mock_contact_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGoogleTokenExpiredHandler:

    def test_returns_401_with_reauth_hint(self, client):
        with patch("app.main.delete_oauth_token", new_callable=AsyncMock) as mock_delete:
            response = client.post("/integration/google-contacts/sync", headers=AUTH)

        assert response.status_code == 401
        assert "google_contacts" in response.json()["detail"]
        assert "/integration/google-contacts/oauth/url" in response.json()["detail"]
        mock_delete.assert_awaited_once()
        assert mock_delete.call_args.args[1] == "google_contacts"


class TestValidationErrorHandler:

    @pytest.fixture
    def client(self):
        from app.main import app
        from app.dependencies import get_conversation_service
        app.dependency_overrides[get_conversation_service] = lambda: AsyncMock()
        yield TestClient(app)
        app.dependency_overrides.clear()

    def test_multipart_body_validation_error_returns_422(self, client):
        # Regression test: the request body (a multipart form) is already
        # consumed by FastAPI's form parsing by the time this fails validation,
        # so the handler must not try to re-read it via request.body().
        response = client.post(
            "/language/conversation/turns/audio",
            headers=AUTH,
            data={"thread_id": "undefined"},
            files={"audio": ("clip.ogg", b"fake-audio-bytes", "audio/ogg")},
        )

        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "thread_id"]
