from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.integrations.leetcode.client import LeetCodeAuthError

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_leetcode_service():
    svc = AsyncMock()
    svc.sync.return_value = 3
    return svc


@pytest.fixture
def client(mock_leetcode_service):
    from app.main import app
    from app.dependencies import get_leetcode_sync_service
    app.dependency_overrides[get_leetcode_sync_service] = lambda: mock_leetcode_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestSyncLeetCode:
    def test_returns_synced_count(self, client):
        response = client.post("/cs/platforms/leetcode/sync", headers=AUTH)
        assert response.status_code == 200
        assert response.json() == {"synced": 3}

    def test_returns_502_with_refresh_hint_when_session_is_rejected(self, client, mock_leetcode_service):
        mock_leetcode_service.sync.side_effect = LeetCodeAuthError("LeetCode session cookie may have expired")
        response = client.post("/cs/platforms/leetcode/sync", headers=AUTH)
        assert response.status_code == 502
        assert "LEETCODE_SESSION" in response.json()["detail"]
