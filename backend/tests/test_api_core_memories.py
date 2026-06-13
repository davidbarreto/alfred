from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.features.core.memories.schemas import MemoryRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _memory_read(**kwargs):
    defaults = dict(
        id=1,
        category="fact",
        content="Paris is the capital of France",
        importance=0.8,
        confidence=1.0,
        active=True,
        expires_at=None,
        extra_metadata=None,
        origin_message_id=None,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    defaults.update(kwargs)
    return MemoryRead(**defaults)


@pytest.fixture
def mock_service():
    from unittest.mock import AsyncMock
    svc = AsyncMock()
    svc.get.return_value = _memory_read()
    svc.list.return_value = [_memory_read()]
    svc.create.return_value = _memory_read(id=2, content="New memory")
    svc.update.return_value = _memory_read(active=False)
    svc.delete.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_memory_service
    app.dependency_overrides[get_memory_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListMemories:
    def test_returns_list(self, client):
        response = client.get("/core/memories/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["category"] == "fact"

    def test_requires_auth(self, client):
        assert client.get("/core/memories/").status_code == 403

    def test_category_filter_passed_to_service(self, client, mock_service):
        client.get("/core/memories/?category=fact", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.category == "fact"

    def test_active_filter_passed_to_service(self, client, mock_service):
        client.get("/core/memories/?active=true", headers=AUTH)
        filters = mock_service.list.call_args[0][0]
        assert filters.active is True


class TestGetMemory:
    def test_returns_memory(self, client):
        response = client.get("/core/memories/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.get.return_value = None
        assert client.get("/core/memories/999", headers=AUTH).status_code == 404


class TestCreateMemory:
    def test_creates_and_returns_201(self, client):
        payload = {"category": "fact", "content": "New memory"}
        response = client.post("/core/memories/", json=payload, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["content"] == "New memory"

    def test_invalid_category_rejected(self, client):
        payload = {"category": "invalid_cat", "content": "test"}
        assert client.post("/core/memories/", json=payload, headers=AUTH).status_code == 422


class TestUpdateMemory:
    def test_updates_and_returns_memory(self, client):
        response = client.patch("/core/memories/1", json={"active": False}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["active"] is False

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.update.return_value = None
        assert client.patch("/core/memories/999", json={"active": False}, headers=AUTH).status_code == 404


class TestDeleteMemory:
    def test_deletes_and_returns_204(self, client):
        assert client.delete("/core/memories/1", headers=AUTH).status_code == 204

    def test_returns_404_when_not_found(self, client, mock_service):
        mock_service.delete.return_value = False
        assert client.delete("/core/memories/999", headers=AUTH).status_code == 404
