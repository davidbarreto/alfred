from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_api_request_service
    app.dependency_overrides[get_api_request_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetSummary:
    def test_returns_summary_with_default_window(self, client, mock_service):
        from app.features.core.api_requests.schemas import ApiUsageSummary, ClientUsage, RouteUsage

        mock_service.get_summary.return_value = ApiUsageSummary(
            days=7,
            total=3,
            by_client=[ClientUsage(client="web", requests=3, errors=1, avg_latency_ms=15.5)],
            top_routes=[RouteUsage(client="web", method="GET", route="/organizer/tasks", requests=3, errors=1)],
        )

        response = client.get("/core/api-requests/summary", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["by_client"][0] == {"client": "web", "requests": 3, "errors": 1, "avg_latency_ms": 15.5}
        assert body["top_routes"][0]["route"] == "/organizer/tasks"
        mock_service.get_summary.assert_awaited_once_with(days=7)

    def test_passes_days_query_param(self, client, mock_service):
        from app.features.core.api_requests.schemas import ApiUsageSummary

        mock_service.get_summary.return_value = ApiUsageSummary(days=30, total=0, by_client=[], top_routes=[])

        client.get("/core/api-requests/summary?days=30", headers=AUTH)

        mock_service.get_summary.assert_awaited_once_with(days=30)

    @pytest.mark.parametrize("days", [0, 91])
    def test_rejects_out_of_range_days(self, client, days):
        assert client.get(f"/core/api-requests/summary?days={days}", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/core/api-requests/summary").status_code == 403
