import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

AUTH = {"Authorization": "Bearer test-api-token"}
TOKEN = "test-api-token"


async def _ok_stream():
    yield "Hello"
    yield ", world"


async def _empty_stream():
    return
    yield  # make it an async generator


@pytest.fixture
def mock_chat_service():
    svc = AsyncMock()
    # stream_chat is an async generator — use MagicMock so calling it returns
    # the generator directly without an extra coroutine wrapper.
    svc.stream_chat = MagicMock(side_effect=lambda req: _ok_stream())
    return svc


@pytest.fixture
def client(mock_chat_service):
    from app.main import app
    from app.dependencies import get_chat_service
    app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestChatStream:
    def test_requires_token_param(self, client):
        response = client.get("/core/chats/stream?session_id=1", headers={})
        assert response.status_code == 401

    def test_wrong_token_rejected(self, client):
        response = client.get("/core/chats/stream?session_id=1&token=bad", headers={})
        assert response.status_code == 401

    def test_valid_token_returns_200(self, client):
        response = client.get(f"/core/chats/stream?session_id=1&token={TOKEN}", headers={})
        assert response.status_code == 200

    def test_content_type_is_event_stream(self, client):
        response = client.get(f"/core/chats/stream?session_id=1&token={TOKEN}", headers={})
        assert "text/event-stream" in response.headers["content-type"]

    def test_response_contains_chunks(self, client):
        response = client.get(f"/core/chats/stream?session_id=1&token={TOKEN}", headers={})
        body = response.text
        assert "Hello" in body
        assert ", world" in body

    def test_response_ends_with_done(self, client):
        response = client.get(f"/core/chats/stream?session_id=1&token={TOKEN}", headers={})
        assert "[DONE]" in response.text

    def test_stream_chat_called_with_session_id(self, client, mock_chat_service):
        client.get(f"/core/chats/stream?session_id=42&token={TOKEN}", headers={})
        call_arg = mock_chat_service.stream_chat.call_args[0][0]
        assert call_arg.session_id == 42
