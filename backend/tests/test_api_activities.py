from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.activities.schemas import (
    ActivityLogRead,
    ActivityRead,
    ActivityStats,
    WeekStat,
)
from app.features.organizer.activities.service import ActivityStateError, ActivityValidationError

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)


def _activity(**kw) -> ActivityRead:
    defaults = dict(id=1, title="Gym", tags=["health"], created_at=_NOW, updated_at=_NOW)
    defaults.update(kw)
    return ActivityRead(**defaults)


def _log(**kw) -> ActivityLogRead:
    defaults = dict(id=1, activity_id=1, done_at=datetime(2026, 10, 21, 8, 0), minutes=60, created_at=_NOW, updated_at=_NOW)
    defaults.update(kw)
    return ActivityLogRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.create_activity.return_value = _activity(id=2)
    svc.get_activities.return_value = [_activity()]
    svc.get_activity.return_value = _activity()
    svc.update_activity.return_value = _activity(title="Renamed")
    svc.archive.return_value = _activity(archived_at=_NOW)
    svc.unarchive.return_value = _activity()
    svc.log.return_value = _log()
    svc.get_history.return_value = [_log()]
    svc.get_stats.return_value = ActivityStats(
        weeks=[WeekStat(week_start=date(2026, 10, 19), count=1, minutes=60)], by_activity=[], by_tag=[],
        total_count=1, total_minutes=60,
    )
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_activity_service

    app.dependency_overrides[get_activity_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestCrud:
    def test_create(self, client):
        response = client.post("/organizer/activities", json={"title": "Gym", "tags": ["health"], "target_per_week": 3}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["id"] == 2

    @pytest.mark.parametrize("body", [{"title": ""}, {"title": "x", "context": "office"}, {"title": "x", "min_minutes": 90, "max_minutes": 30}])
    def test_invalid_create_is_422(self, client, body):
        assert client.post("/organizer/activities", json=body, headers=AUTH).status_code == 422

    def test_list_passes_filters(self, client, mock_service):
        response = client.get("/organizer/activities?include_archived=true&tag=health&q=gy", headers=AUTH)
        assert response.status_code == 200
        filters = mock_service.get_activities.call_args.args[0]
        assert (filters.include_archived, filters.tag, filters.q) == (True, "health", "gy")

    def test_get_and_404(self, client, mock_service):
        assert client.get("/organizer/activities/1", headers=AUTH).json()["title"] == "Gym"
        mock_service.get_activity.return_value = None
        assert client.get("/organizer/activities/9", headers=AUTH).status_code == 404

    def test_update(self, client):
        response = client.patch("/organizer/activities/1", json={"title": "Renamed"}, headers=AUTH)
        assert response.json()["title"] == "Renamed"

    def test_update_404_and_422(self, client, mock_service):
        mock_service.update_activity.return_value = None
        assert client.patch("/organizer/activities/9", json={"title": "x"}, headers=AUTH).status_code == 404
        mock_service.update_activity.side_effect = ActivityValidationError("range")
        assert client.patch("/organizer/activities/1", json={"max_minutes": 5}, headers=AUTH).status_code == 422

    def test_archive_unarchive(self, client, mock_service):
        assert client.post("/organizer/activities/1/archive", headers=AUTH).json()["archived_at"] is not None
        assert client.post("/organizer/activities/1/unarchive", headers=AUTH).json()["archived_at"] is None
        mock_service.archive.return_value = None
        assert client.post("/organizer/activities/9/archive", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.get("/organizer/activities").status_code == 403


class TestLogs:
    def test_log(self, client, mock_service):
        response = client.post(
            "/organizer/activities/1/logs", json={"minutes": 60, "note": "Legs", "done_at": "2026-10-20T19:00:00"}, headers=AUTH
        )
        assert response.status_code == 201
        assert mock_service.log.call_args.args[1].minutes == 60

    def test_bare_log(self, client):
        assert client.post("/organizer/activities/1/logs", json={}, headers=AUTH).status_code == 201

    def test_invalid_minutes_is_422(self, client):
        assert client.post("/organizer/activities/1/logs", json={"minutes": 0}, headers=AUTH).status_code == 422

    def test_future_is_422_archived_is_409_unknown_is_404(self, client, mock_service):
        mock_service.log.side_effect = ActivityValidationError("future")
        assert client.post("/organizer/activities/1/logs", json={}, headers=AUTH).status_code == 422
        mock_service.log.side_effect = ActivityStateError("archived")
        assert client.post("/organizer/activities/1/logs", json={}, headers=AUTH).status_code == 409
        mock_service.log.side_effect = None
        mock_service.log.return_value = None
        assert client.post("/organizer/activities/9/logs", json={}, headers=AUTH).status_code == 404

    def test_history(self, client, mock_service):
        response = client.get("/organizer/activities/1/logs?limit=10&offset=5", headers=AUTH)
        assert response.status_code == 200 and response.json()[0]["minutes"] == 60
        mock_service.get_history.assert_awaited_once_with(1, 10, 5)

    def test_history_404(self, client, mock_service):
        mock_service.get_history.return_value = None
        assert client.get("/organizer/activities/9/logs", headers=AUTH).status_code == 404


class TestStats:
    def test_stats_route_is_not_shadowed_by_the_id_route(self, client, mock_service):
        response = client.get("/organizer/activities/stats?weeks=4", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["total_minutes"] == 60
        mock_service.get_stats.assert_awaited_once_with(4)

    def test_default_weeks(self, client, mock_service):
        client.get("/organizer/activities/stats", headers=AUTH)
        mock_service.get_stats.assert_awaited_once_with(12)

    @pytest.mark.parametrize("weeks", [0, 105])
    def test_weeks_are_bounded(self, client, weeks):
        assert client.get(f"/organizer/activities/stats?weeks={weeks}", headers=AUTH).status_code == 422
