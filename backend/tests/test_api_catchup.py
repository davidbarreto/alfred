from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.features.core.catchup.schemas import CatchupApplyRead, CatchupRead, CatchupSuggestion, CatchupTask

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def mock_service():
    return AsyncMock()


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_catchup_service

    app.dependency_overrides[get_catchup_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetCatchup:
    def test_returns_suggestions(self, client, mock_service):
        mock_service.get_suggestions.return_value = CatchupRead(
            today_top=[CatchupTask(id=1, title="Pay invoice", priority="HIGH", urgency="URGENT", days_overdue=2)],
            suggestions=[CatchupSuggestion(kind="habits", title="1 habit(s) you keep missing", detail="d", applicable=False)],
        )

        response = client.get("/core/catchup", headers=AUTH)

        assert response.status_code == 200
        body = response.json()
        assert body["today_top"][0]["title"] == "Pay invoice"
        assert body["suggestions"][0]["kind"] == "habits"
        assert body["suggestions"][0]["applicable"] is False

    def test_requires_auth(self, client):
        assert client.get("/core/catchup").status_code == 403


class TestApplyCatchup:
    def test_applies_spread(self, client, mock_service):
        mock_service.apply.return_value = CatchupApplyRead(kind="spread", applied=4, skipped=0)

        response = client.post("/core/catchup/apply", json={"kind": "spread"}, headers=AUTH)

        assert response.status_code == 200
        assert response.json() == {"kind": "spread", "applied": 4, "skipped": 0}
        (request,), _ = mock_service.apply.call_args
        assert request.kind == "spread"
        assert request.task_ids is None

    def test_applies_drop_with_ids(self, client, mock_service):
        mock_service.apply.return_value = CatchupApplyRead(kind="drop", applied=2, skipped=1)

        response = client.post("/core/catchup/apply", json={"kind": "drop", "task_ids": [3, 4, 5]}, headers=AUTH)

        assert response.status_code == 200
        assert response.json()["skipped"] == 1

    @pytest.mark.parametrize("body", [{"kind": "habits"}, {"kind": "drop", "task_ids": []}, {}])
    def test_rejects_invalid_requests(self, client, body):
        assert client.post("/core/catchup/apply", json=body, headers=AUTH).status_code == 422

    def test_nothing_to_apply_is_a_404(self, client, mock_service):
        mock_service.apply.side_effect = HTTPException(status_code=404, detail="Nothing to spread")

        response = client.post("/core/catchup/apply", json={"kind": "spread"}, headers=AUTH)

        assert response.status_code == 404
        assert response.json()["detail"] == "Nothing to spread"
