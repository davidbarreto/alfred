import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.integrations.embedding_calls.schemas import EmbeddingCallRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _embedding_call_read(**kwargs):
    defaults = dict(
        id=1,
        feature="chat",
        query_text="What did I say about my dentist appointment?",
        source_types=["memory", "note", "task"],
        top_k=5,
        threshold=0.7,
        results=[
            {"id": 10, "source_type": "memory", "source_id": 3, "content": "Dentist on Friday", "similarity": 0.91},
        ],
        result_count=1,
        latency_ms=42,
        created_at=datetime(2026, 6, 16, 10, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return EmbeddingCallRead(**defaults)


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestListEmbeddingCalls:
    def test_returns_list(self, client):
        call = _embedding_call_read()
        with patch(
            "app.api.routes.integrations.embedding_calls.get_embedding_calls",
            new=AsyncMock(return_value=[call]),
        ):
            response = client.get("/integration/embedding-calls/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["feature"] == "chat"
        assert data[0]["top_k"] == 5
        assert data[0]["results"][0]["similarity"] == 0.91

    def test_requires_auth(self, client):
        assert client.get("/integration/embedding-calls/").status_code == 403

    def test_wrong_token_rejected(self, client):
        assert client.get("/integration/embedding-calls/", headers={"Authorization": "Bearer bad"}).status_code == 401

    def test_response_shape(self, client):
        call = _embedding_call_read()
        with patch(
            "app.api.routes.integrations.embedding_calls.get_embedding_calls",
            new=AsyncMock(return_value=[call]),
        ):
            response = client.get("/integration/embedding-calls/", headers=AUTH)
        entry = response.json()[0]
        for field in (
            "id", "feature", "query_text", "source_types", "top_k", "threshold",
            "results", "result_count", "latency_ms", "created_at",
        ):
            assert field in entry

    def test_feature_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.embedding_calls.get_embedding_calls", new=mock_get):
            client.get("/integration/embedding-calls/?feature=recall", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["feature"] == "recall"

    def test_q_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.embedding_calls.get_embedding_calls", new=mock_get):
            client.get("/integration/embedding-calls/?q=dentist", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["q"] == "dentist"

    def test_after_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.embedding_calls.get_embedding_calls", new=mock_get):
            client.get("/integration/embedding-calls/?after=2026-06-01T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["after"] is not None

    def test_before_filter_forwarded(self, client):
        mock_get = AsyncMock(return_value=[])
        with patch("app.api.routes.integrations.embedding_calls.get_embedding_calls", new=mock_get):
            client.get("/integration/embedding-calls/?before=2026-06-17T00:00:00Z", headers=AUTH)
        _, kwargs = mock_get.call_args
        assert kwargs["before"] is not None


class TestGetEmbeddingCall:
    def test_returns_call(self, client):
        call = _embedding_call_read(id=1)
        with patch(
            "app.api.routes.integrations.embedding_calls.get_embedding_call",
            new=AsyncMock(return_value=call),
        ):
            response = client.get("/integration/embedding-calls/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client):
        with patch(
            "app.api.routes.integrations.embedding_calls.get_embedding_call",
            new=AsyncMock(return_value=None),
        ):
            response = client.get("/integration/embedding-calls/99", headers=AUTH)
        assert response.status_code == 404
