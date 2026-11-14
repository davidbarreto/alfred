from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.google_oauth.client import GoogleRequestRejectedError, GoogleTokenExpiredError

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


class TestGoogleRequestRejectedHandler:

    def test_returns_422_with_readable_detail(self, mock_contact_service, client):
        mock_contact_service.sync.side_effect = GoogleRequestRejectedError("google_calendar", 400)

        response = client.post("/integration/google-contacts/sync", headers=AUTH)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "google_calendar" in detail


    def test_shows_googles_own_message_when_it_is_informative(self, mock_contact_service, client):
        response_body = MagicMock()
        response_body.json.return_value = {"error": {"message": "You need to have writer access to this calendar."}}
        mock_contact_service.sync.side_effect = GoogleRequestRejectedError("google_calendar", 403, response_body)

        detail = client.post("/integration/google-contacts/sync", headers=AUTH).json()["detail"]

        assert detail.endswith(": You need to have writer access to this calendar.")

    def test_without_a_google_message_it_only_says_google_rejected_the_change(self, mock_contact_service, client):
        mock_contact_service.sync.side_effect = GoogleRequestRejectedError("google_calendar", 400)

        detail = client.post("/integration/google-contacts/sync", headers=AUTH).json()["detail"]

        assert detail == "Google rejected this change (google_calendar, HTTP 400)"


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
