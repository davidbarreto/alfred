import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.integrations.llm_calls.schemas import LlmCallRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _llm_call_read(**kwargs):
    defaults = dict(
        id=1,
        provider="anthropic",
        model="claude-sonnet-4-6",
        feature="chat",
        prompt=[{"role": "user", "content": "Hello, what is the weather today?"}],
        response="I don't have access to real-time weather data.",
        tokens_input=20,
        tokens_output=15,
        latency_ms=312,
        is_audio=False,
        created_at=datetime(2026, 6, 16, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return LlmCallRead(**defaults)


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestListLlmCalls:
    def test_returns_list(self, client):
        call = _llm_call_read()
        with patch(
            "app.api.routes.integrations.llm_calls.get_llm_calls",
            new=AsyncMock(return_value=[call]),
        ):
            response = client.get("/integration/llm-calls/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["provider"] == "anthropic"
        assert data[0]["model"] == "claude-sonnet-4-6"
        assert data[0]["feature"] == "chat"

    def test_requires_auth(self, client):
        assert client.get("/integration/llm-calls/").status_code == 403

    def test_wrong_token_rejected(self, client):
        assert client.get("/integration/llm-calls/", headers={"Authorization": "Bearer bad"}).status_code == 401

    def test_response_shape(self, client):
        call = _llm_call_read()
        with patch(
            "app.api.routes.integrations.llm_calls.get_llm_calls",
            new=AsyncMock(return_value=[call]),
        ):
            response = client.get("/integration/llm-calls/", headers=AUTH)
        entry = response.json()[0]
        for field in ("id", "provider", "model", "feature", "prompt", "response", "tokens_input", "tokens_output", "latency_ms", "created_at"):
            assert field in entry

    def test_provider_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?provider=anthropic", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["provider"] == "anthropic"

    def test_model_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?model=claude-sonnet-4-6", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["model"] == "claude-sonnet-4-6"

    def test_feature_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?feature=chat", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["feature"] == "chat"

    def test_q_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?q=weather", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["q"] == "weather"

    def test_after_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?after=2026-06-01T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["after"] is not None

    def test_before_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.llm_calls.get_llm_calls", new=mock_get):
            client.get("/integration/llm-calls/?before=2026-06-17T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["before"] is not None


class TestGetLlmCall:
    def test_returns_call(self, client):
        call = _llm_call_read(id=1)
        with patch(
            "app.api.routes.integrations.llm_calls.get_llm_call",
            new=AsyncMock(return_value=call),
        ):
            response = client.get("/integration/llm-calls/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client):
        with patch(
            "app.api.routes.integrations.llm_calls.get_llm_call",
            new=AsyncMock(return_value=None),
        ):
            response = client.get("/integration/llm-calls/99", headers=AUTH)
        assert response.status_code == 404
