import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.organizer.calendar_events.schemas import EventRead

AUTH = {"Authorization": "Bearer test-api-token"}

_START = datetime(2026, 6, 15, 10, 0)
_END = datetime(2026, 6, 15, 11, 0)


def _event_read(**kwargs):
    defaults = dict(
        id=1,
        title="Team Sync",
        description=None,
        location=None,
        start_datetime=_START,
        end_datetime=_END,
        all_day=False,
        host=None,
        invitees=[],
        tags=[],
        recurrence_rule=None,
    )
    defaults.update(kwargs)
    return EventRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_event.return_value = _event_read()
    svc.get_events.return_value = [_event_read()]
    svc.create_event.return_value = _event_read(id=2, title="New Event")
    svc.update_event.return_value = _event_read(title="Updated Event")
    svc.delete_event.return_value = None
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_calendar_event_service
    app.dependency_overrides[get_calendar_event_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetEvents:
    def test_returns_list(self, client):
        response = client.get("/organizer/calendar-events/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Team Sync"

    def test_requires_auth(self, client):
        response = client.get("/organizer/calendar-events/")
        assert response.status_code == 403

    def test_wrong_token_rejected(self, client):
        response = client.get("/organizer/calendar-events/", headers={"Authorization": "Bearer bad-token"})
        assert response.status_code == 401

    def test_tags_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/calendar-events/?tags=work&tags=personal", headers=AUTH)
        filters = mock_service.get_events.call_args[0][0]
        assert filters.tags == ["work", "personal"]

    def test_start_from_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/calendar-events/?start_from=2026-06-01T00:00:00", headers=AUTH)
        filters = mock_service.get_events.call_args[0][0]
        assert filters.start_from is not None

    def test_start_to_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/calendar-events/?start_to=2026-06-30T23:59:59", headers=AUTH)
        filters = mock_service.get_events.call_args[0][0]
        assert filters.start_to is not None

    def test_limit_filter_passed_to_service(self, client, mock_service):
        client.get("/organizer/calendar-events/?limit=10", headers=AUTH)
        filters = mock_service.get_events.call_args[0][0]
        assert filters.limit == 10

    def test_default_filters_when_no_params(self, client, mock_service):
        client.get("/organizer/calendar-events/", headers=AUTH)
        filters = mock_service.get_events.call_args[0][0]
        assert filters.tags is None
        assert filters.start_from is None
        assert filters.start_to is None
        assert filters.limit == 100


class TestGetEvent:
    def test_found_returns_200(self, client):
        response = client.get("/organizer/calendar-events/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get_event.return_value = None
        response = client.get("/organizer/calendar-events/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Event not found"

    def test_requires_auth(self, client):
        response = client.get("/organizer/calendar-events/1")
        assert response.status_code == 403


class TestCreateEvent:
    def test_creates_and_returns_201(self, client):
        payload = {
            "title": "Q4 Kickoff",
            "start_datetime": "2026-06-15T10:00:00",
            "end_datetime": "2026-06-15T11:00:00",
        }
        response = client.post("/organizer/calendar-events/", json=payload, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["title"] == "New Event"

    def test_creates_with_host_and_invitees(self, client, mock_service):
        mock_service.create_event.return_value = _event_read(
            id=3,
            title="Team Meeting",
            host="alice@example.com",
            invitees=["bob@example.com", "carol@example.com"],
        )
        payload = {
            "title": "Team Meeting",
            "start_datetime": "2026-06-15T10:00:00",
            "end_datetime": "2026-06-15T11:00:00",
            "host": "alice@example.com",
            "invitees": ["bob@example.com", "carol@example.com"],
        }
        response = client.post("/organizer/calendar-events/", json=payload, headers=AUTH)
        assert response.status_code == 201
        data = response.json()
        assert data["host"] == "alice@example.com"
        assert data["invitees"] == ["bob@example.com", "carol@example.com"]

    def test_requires_auth(self, client):
        payload = {
            "title": "Q4 Kickoff",
            "start_datetime": "2026-06-15T10:00:00",
            "end_datetime": "2026-06-15T11:00:00",
        }
        response = client.post("/organizer/calendar-events/", json=payload)
        assert response.status_code == 403

    def test_missing_required_fields_returns_422(self, client):
        response = client.post("/organizer/calendar-events/", json={"title": "No dates"}, headers=AUTH)
        assert response.status_code == 422

    def test_missing_title_returns_422(self, client):
        payload = {
            "start_datetime": "2026-06-15T10:00:00",
            "end_datetime": "2026-06-15T11:00:00",
        }
        response = client.post("/organizer/calendar-events/", json=payload, headers=AUTH)
        assert response.status_code == 422


class TestUpdateEvent:
    def test_updates_and_returns_200(self, client):
        payload = {"title": "Updated Event"}
        response = client.patch("/organizer/calendar-events/1", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Event"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update_event.return_value = None
        response = client.patch("/organizer/calendar-events/999", json={"title": "X"}, headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.patch("/organizer/calendar-events/1", json={"title": "X"})
        assert response.status_code == 403

    def test_update_host_and_invitees(self, client, mock_service):
        mock_service.update_event.return_value = _event_read(
            host="new@example.com",
            invitees=["guest@example.com"],
        )
        payload = {"host": "new@example.com", "invitees": ["guest@example.com"]}
        response = client.patch("/organizer/calendar-events/1", json=payload, headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["host"] == "new@example.com"
        assert data["invitees"] == ["guest@example.com"]

    def test_invalid_event_id_type(self, client):
        response = client.patch("/organizer/calendar-events/not-an-int", json={"title": "X"}, headers=AUTH)
        assert response.status_code == 422


class TestDeleteEvent:
    def test_deletes_returns_204(self, client):
        response = client.delete("/organizer/calendar-events/1", headers=AUTH)
        assert response.status_code == 204

    def test_requires_auth(self, client):
        response = client.delete("/organizer/calendar-events/1")
        assert response.status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/organizer/calendar-events/42", headers=AUTH)
        mock_service.delete_event.assert_called_once_with(42)
