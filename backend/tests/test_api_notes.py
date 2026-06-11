import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.organizer.notes.schemas import NoteRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _note_read(**kwargs):
    defaults = dict(id=1, title="Test Note", description="Some content", tags=[], task_id=None)
    defaults.update(kwargs)
    return NoteRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_note.return_value = _note_read()
    svc.get_notes.return_value = [_note_read()]
    svc.create_note.return_value = _note_read(id=2, title="New Note")
    svc.update_note.return_value = _note_read(title="Updated Note")
    svc.delete_note.return_value = None
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_note_service
    app.dependency_overrides[get_note_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetNotes:
    def test_returns_list(self, client):
        response = client.get("/notes/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Note"

    def test_requires_auth(self, client):
        response = client.get("/notes/")
        assert response.status_code == 403

    def test_wrong_token_rejected(self, client):
        response = client.get("/notes/", headers={"Authorization": "Bearer bad-token"})
        assert response.status_code == 401

    def test_tags_filter_passed_to_service(self, client, mock_service):
        client.get("/notes/?tags=work&tags=ideas", headers=AUTH)
        filters = mock_service.get_notes.call_args[0][0]
        assert filters.tags == ["work", "ideas"]

    def test_task_id_filter_passed_to_service(self, client, mock_service):
        client.get("/notes/?task_id=5", headers=AUTH)
        filters = mock_service.get_notes.call_args[0][0]
        assert filters.task_id == 5

    def test_limit_filter_passed_to_service(self, client, mock_service):
        client.get("/notes/?limit=10", headers=AUTH)
        filters = mock_service.get_notes.call_args[0][0]
        assert filters.limit == 10

    def test_default_filters_when_no_params(self, client, mock_service):
        client.get("/notes/", headers=AUTH)
        filters = mock_service.get_notes.call_args[0][0]
        assert filters.tags is None
        assert filters.task_id is None
        assert filters.limit == 100


class TestGetNote:
    def test_found_returns_200(self, client):
        response = client.get("/notes/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get_note.return_value = None
        response = client.get("/notes/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Note not found"

    def test_requires_auth(self, client):
        response = client.get("/notes/1")
        assert response.status_code == 403


class TestCreateNote:
    def test_creates_and_returns_201(self, client):
        payload = {"title": "Meeting notes", "description": "Discussed Q4 goals"}
        response = client.post("/notes/", json=payload, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["title"] == "New Note"

    def test_requires_auth(self, client):
        response = client.post("/notes/", json={"title": "T"})
        assert response.status_code == 403

    def test_missing_title_returns_422(self, client):
        response = client.post("/notes/", json={"description": "No title"}, headers=AUTH)
        assert response.status_code == 422


class TestUpdateNote:
    def test_updates_and_returns_200(self, client):
        payload = {"title": "Updated Note"}
        response = client.patch("/notes/1", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["title"] == "Updated Note"

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.update_note.return_value = None
        response = client.patch("/notes/999", json={"title": "X"}, headers=AUTH)
        assert response.status_code == 404

    def test_requires_auth(self, client):
        response = client.patch("/notes/1", json={"title": "X"})
        assert response.status_code == 403

    def test_invalid_note_id_type(self, client):
        response = client.patch("/notes/not-an-int", json={"title": "X"}, headers=AUTH)
        assert response.status_code == 422


class TestDeleteNote:
    def test_deletes_returns_204(self, client):
        response = client.delete("/notes/1", headers=AUTH)
        assert response.status_code == 204

    def test_requires_auth(self, client):
        response = client.delete("/notes/1")
        assert response.status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/notes/42", headers=AUTH)
        mock_service.delete_note.assert_called_once_with(42)
