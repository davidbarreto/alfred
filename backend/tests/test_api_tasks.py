import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.features.organizer.tasks.schemas import TaskRead

AUTH = {"Authorization": "Bearer test-api-token"}


def _task_read(**kwargs):
    defaults = dict(
        id=1, title="Test Task", status="TODO",
        priority="LOW", urgency="NORMAL", tags=[]
    )
    defaults.update(kwargs)
    return TaskRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_task.return_value = _task_read()
    svc.get_tasks.return_value = [_task_read()]
    svc.create_task.return_value = _task_read(id=2, title="New Task")
    svc.update_task.return_value = _task_read(status="DONE")
    svc.delete_task.return_value = None
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_task_service
    app.dependency_overrides[get_task_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestGetTasks:
    def test_returns_list(self, client):
        response = client.get("/tasks/", headers=AUTH)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["title"] == "Test Task"

    def test_requires_auth(self, client):
        response = client.get("/tasks/")
        assert response.status_code == 403

    def test_wrong_token_rejected(self, client):
        response = client.get("/tasks/", headers={"Authorization": "Bearer bad-token"})
        assert response.status_code == 401

    def test_status_filter_passed_to_service(self, client, mock_service):
        client.get("/tasks/?status=TODO", headers=AUTH)
        filters = mock_service.get_tasks.call_args[0][0]
        assert filters.status == "TODO"

    def test_priority_filter_passed_to_service(self, client, mock_service):
        client.get("/tasks/?priority=HIGH", headers=AUTH)
        filters = mock_service.get_tasks.call_args[0][0]
        assert filters.priority == "HIGH"

    def test_tags_filter_passed_to_service(self, client, mock_service):
        client.get("/tasks/?tags=work&tags=urgent", headers=AUTH)
        filters = mock_service.get_tasks.call_args[0][0]
        assert filters.tags == ["work", "urgent"]

    def test_limit_filter_passed_to_service(self, client, mock_service):
        client.get("/tasks/?limit=10", headers=AUTH)
        filters = mock_service.get_tasks.call_args[0][0]
        assert filters.limit == 10

    def test_default_filters_when_no_params(self, client, mock_service):
        client.get("/tasks/", headers=AUTH)
        filters = mock_service.get_tasks.call_args[0][0]
        assert filters.status == "ALL"
        assert filters.priority == "ALL"
        assert filters.tags is None
        assert filters.limit == 100

    def test_invalid_status_returns_422(self, client):
        response = client.get("/tasks/?status=INVALID", headers=AUTH)
        assert response.status_code == 422


class TestGetTask:
    def test_found_returns_200(self, client):
        response = client.get("/tasks/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_not_found_returns_404(self, client, mock_service):
        mock_service.get_task.return_value = None
        response = client.get("/tasks/999", headers=AUTH)
        assert response.status_code == 404
        assert response.json()["detail"] == "Task not found"

    def test_requires_auth(self, client):
        response = client.get("/tasks/1")
        assert response.status_code == 403


class TestCreateTask:
    def test_creates_and_returns_201(self, client):
        payload = {
            "title": "New Task",
            "status": "TODO",
            "priority": "LOW",
            "urgency": "NORMAL",
        }
        response = client.post("/tasks/", json=payload, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["title"] == "New Task"

    def test_requires_auth(self, client):
        response = client.post("/tasks/", json={"title": "T"})
        assert response.status_code == 403

    def test_validates_status_field(self, client):
        payload = {"title": "Task", "status": "INVALID_STATUS"}
        response = client.post("/tasks/", json=payload, headers=AUTH)
        assert response.status_code == 422


class TestUpdateTask:
    def test_updates_and_returns_200(self, client):
        payload = {"status": "DONE"}
        response = client.patch("/tasks/1", json=payload, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "DONE"

    def test_requires_auth(self, client):
        response = client.patch("/tasks/1", json={"status": "DONE"})
        assert response.status_code == 403

    def test_invalid_task_id_type(self, client):
        response = client.patch("/tasks/not-an-int", json={"status": "DONE"}, headers=AUTH)
        assert response.status_code == 422


class TestDeleteTask:
    def test_deletes_returns_204(self, client):
        response = client.delete("/tasks/1", headers=AUTH)
        assert response.status_code == 204

    def test_requires_auth(self, client):
        response = client.delete("/tasks/1")
        assert response.status_code == 403

    def test_service_called_with_correct_id(self, client, mock_service):
        client.delete("/tasks/42", headers=AUTH)
        mock_service.delete_task.assert_called_once_with(42)
