from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.core.messages.schemas import MessageIngestResponse, MessageRead
from app.features.core.sessions.schemas import SessionRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _message_read(**kwargs) -> MessageRead:
    defaults = dict(
        id=1,
        session_id=1,
        role="user",
        content="hello",
        created_at=datetime(2026, 1, 1),
    )
    defaults.update(kwargs)
    return MessageRead(**defaults)


def _session_read(**kwargs) -> SessionRead:
    defaults = dict(
        id=1,
        source="telegram",
        external_id="chat_123",
        summary=None,
        last_interaction_at=datetime(2026, 1, 1),
        created_at=datetime(2026, 1, 1),
        finished_at=None,
    )
    defaults.update(kwargs)
    return SessionRead(**defaults)


@pytest.fixture
def mock_message_service():
    svc = AsyncMock()
    svc.get.return_value = _message_read()
    svc.list.return_value = [_message_read()]
    svc.create.return_value = _message_read(id=2)
    return svc


@pytest.fixture
def mock_session_service():
    svc = AsyncMock()
    svc.get_or_create_active.return_value = (_session_read(id=10), False)
    return svc


@pytest.fixture
def mock_summary_service():
    svc = AsyncMock()
    svc.summarise_and_save = AsyncMock()
    return svc


@pytest.fixture
def client(mock_message_service, mock_session_service, mock_summary_service):
    from app.main import app
    from app.dependencies import get_message_service, get_session_service, get_session_summary_service
    app.dependency_overrides[get_message_service] = lambda: mock_message_service
    app.dependency_overrides[get_session_service] = lambda: mock_session_service
    app.dependency_overrides[get_session_summary_service] = lambda: mock_summary_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestIngestMessage:
    def test_returns_201_with_message_and_session_ids(self, client, mock_message_service):
        mock_message_service.create.return_value = _message_read(id=99, session_id=10)
        response = client.post(
            "/core/messages/",
            json={"text": "buy milk", "source": "telegram", "external_id": "chat_123"},
            headers=AUTH,
        )
        assert response.status_code == 201
        body = response.json()
        assert body["message_id"] == 99
        assert body["session_id"] == 10

    def test_calls_get_or_create_active_with_source_and_external_id(self, client, mock_session_service):
        client.post(
            "/core/messages/",
            json={"text": "hi", "source": "telegram", "external_id": "chat_42"},
            headers=AUTH,
        )
        mock_session_service.get_or_create_active.assert_called_once_with("telegram", "chat_42")

    def test_creates_user_role_message(self, client, mock_message_service):
        client.post(
            "/core/messages/",
            json={"text": "hello", "source": "telegram", "external_id": "chat_1"},
            headers=AUTH,
        )
        created = mock_message_service.create.call_args[0][0]
        assert created.role == "user"
        assert created.content == "hello"

    def test_passes_meta_when_provided(self, client, mock_message_service):
        client.post(
            "/core/messages/",
            json={"text": "hi", "source": "telegram", "external_id": "chat_1", "meta": {"message_id": 12345}},
            headers=AUTH,
        )
        created = mock_message_service.create.call_args[0][0]
        assert created.meta == {"message_id": 12345}

    def test_requires_auth(self, client):
        response = client.post(
            "/core/messages/",
            json={"text": "hi", "source": "telegram", "external_id": "chat_1"},
        )
        assert response.status_code == 403

    def test_invalid_source_returns_422(self, client):
        response = client.post(
            "/core/messages/",
            json={"text": "hi", "source": "fax", "external_id": "chat_1"},
            headers=AUTH,
        )
        assert response.status_code == 422


class TestListMessages:
    def test_returns_list(self, client):
        response = client.get("/core/messages/", headers=AUTH)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_requires_auth(self, client):
        assert client.get("/core/messages/").status_code == 403


class TestGetMessage:
    def test_returns_message(self, client):
        response = client.get("/core/messages/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1
        assert response.json()["role"] == "user"
        assert response.json()["content"] == "hello"

    def test_returns_404_when_not_found(self, client, mock_message_service):
        mock_message_service.get.return_value = None
        assert client.get("/core/messages/999", headers=AUTH).status_code == 404
