import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def _task_read_mock(id=1, title="Buy milk", status="TODO", priority="LOW", tags=None, deadline=None):
    m = MagicMock()
    m.model_dump.return_value = {
        "id": id,
        "title": title,
        "status": status,
        "priority": priority,
        "urgency": "NORMAL",
        "deadline": deadline,
        "tags": tags or [],
        "recurrence_rule": None,
    }
    return m


def _note_read_mock(id=1, title="Some note", tags=None):
    m = MagicMock()
    m.model_dump.return_value = {
        "id": id,
        "title": title,
        "content": "",
        "tags": tags or [],
    }
    return m


def _override_services(app, task_svc=None, note_svc=None):
    from app.dependencies import (
        get_task_service, get_note_service, get_calendar_event_service,
        get_transaction_service, get_account_service, get_budget_target_service,
        get_category_service,
        get_recurring_transaction_service, get_command_execution_service,
        get_production_service,
    )
    mock_cmd_exec = AsyncMock()
    mock_cmd_exec.create.return_value = MagicMock(id=99)
    mock_cmd_exec.update = AsyncMock()
    app.dependency_overrides[get_command_execution_service] = lambda: mock_cmd_exec

    for dep, svc in [
        (get_task_service, task_svc),
        (get_note_service, note_svc),
        (get_calendar_event_service, None),
        (get_transaction_service, None),
        (get_account_service, None),
        (get_budget_target_service, None),
        (get_category_service, None),
        (get_recurring_transaction_service, None),
        (get_production_service, None),
    ]:
        app.dependency_overrides[dep] = lambda s=svc: s or AsyncMock()

    return mock_cmd_exec


class TestExecuteRoute:
    def test_requires_auth(self, client):
        response = client.post(
            "/commands/execute",
            json={"message_id": 1, "type": "task", "command": "add", "args": {}},
        )
        assert response.status_code == 403

    def test_missing_fields_returns_422(self, client):
        from app.main import app
        _override_services(app)
        try:
            response = client.post("/commands/execute", json={"type": "task"}, headers=AUTH)
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_unknown_type_returns_400(self, client):
        from app.main import app
        _override_services(app)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "unknown", "command": "add", "args": {}},
                headers=AUTH,
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_task_add(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.create_task.return_value = _task_read_mock(title="Buy milk")
        _override_services(app, task_svc=mock_svc)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "task", "command": "add", "args": {"task": "Buy milk"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["type"] == "task"
            assert data["command"] == "add"
            assert data["result"]["title"] == "Buy milk"
            assert "command_execution_id" in data
        finally:
            app.dependency_overrides.clear()

    def test_task_complete(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.complete_task.return_value = _task_read_mock(id=42, status="DONE")
        _override_services(app, task_svc=mock_svc)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "task", "command": "complete", "args": {"id": "42"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            assert response.json()["result"]["status"] == "DONE"
        finally:
            app.dependency_overrides.clear()

    def test_task_delete(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.delete_task.return_value = None
        _override_services(app, task_svc=mock_svc)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "task", "command": "delete", "args": {"id": "7"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["result"]["deleted"] is True
            assert data["result"]["id"] == 7
        finally:
            app.dependency_overrides.clear()

    def test_note_add(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.create_note.return_value = _note_read_mock(title="chocolate is good")
        _override_services(app, note_svc=mock_svc)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "note", "command": "add", "args": {"content": "chocolate is good"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["result"]["title"] == "chocolate is good"
        finally:
            app.dependency_overrides.clear()

    def test_task_not_found_returns_404(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.complete_task.return_value = None
        _override_services(app, task_svc=mock_svc)
        try:
            response = client.post(
                "/commands/execute",
                json={"message_id": 1, "type": "task", "command": "complete", "args": {"id": "999"}},
                headers=AUTH,
            )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_creates_pending_execution_before_running(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.create_task.return_value = _task_read_mock()
        mock_cmd_exec = _override_services(app, task_svc=mock_svc)
        try:
            client.post(
                "/commands/execute",
                json={"message_id": 5, "type": "task", "command": "add", "args": {"task": "x"}},
                headers=AUTH,
            )
            created = mock_cmd_exec.create.call_args[0][0]
            assert created.message_id == 5
            assert created.command_name == "task.add"
            assert created.status == "pending"
        finally:
            app.dependency_overrides.clear()

    def test_updates_execution_to_success_after_run(self, client):
        from app.main import app
        mock_svc = AsyncMock()
        mock_svc.create_task.return_value = _task_read_mock(id=10)
        mock_cmd_exec = _override_services(app, task_svc=mock_svc)
        try:
            client.post(
                "/commands/execute",
                json={"message_id": 5, "type": "task", "command": "add", "args": {"task": "x"}},
                headers=AUTH,
            )
            update_data = mock_cmd_exec.update.call_args[0][1]
            assert update_data.status == "success"
            assert update_data.entity_type == "task"
            assert update_data.entity_id == 10
            assert update_data.executed_at is not None
        finally:
            app.dependency_overrides.clear()
