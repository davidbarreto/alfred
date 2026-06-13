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
        "description": "",
        "tags": tags or [],
    }
    return m


class TestExecuteRoute:
    def test_requires_auth(self, client):
        response = client.post("/commands/execute", json={"type": "task", "command": "add", "arguments": {}})
        assert response.status_code == 403

    def test_missing_fields_returns_422(self, client):
        response = client.post("/commands/execute", json={"type": "task"}, headers=AUTH)
        assert response.status_code == 422

    def test_unknown_type_returns_400(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        for dep in (get_task_service, get_note_service, get_calendar_event_service,
                    get_transaction_service, get_account_service, get_budget_service,
                    get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "unknown", "command": "add", "arguments": {}},
                headers=AUTH,
            )
            assert response.status_code == 400
        finally:
            app.dependency_overrides.clear()

    def test_task_add(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        mock_svc = AsyncMock()
        mock_svc.create_task.return_value = _task_read_mock(title="Buy milk")

        app.dependency_overrides[get_task_service] = lambda: mock_svc
        for dep in (get_note_service, get_calendar_event_service, get_transaction_service,
                    get_account_service, get_budget_service, get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "task", "command": "add", "arguments": {"task": "Buy milk"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["type"] == "task"
            assert data["command"] == "add"
            assert data["result"]["title"] == "Buy milk"
        finally:
            app.dependency_overrides.clear()

    def test_task_complete(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        mock_svc = AsyncMock()
        mock_svc.update_task.return_value = _task_read_mock(id=42, status="DONE")

        app.dependency_overrides[get_task_service] = lambda: mock_svc
        for dep in (get_note_service, get_calendar_event_service, get_transaction_service,
                    get_account_service, get_budget_service, get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "task", "command": "complete", "arguments": {"id": "42"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["result"]["status"] == "DONE"
        finally:
            app.dependency_overrides.clear()

    def test_task_delete(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        mock_svc = AsyncMock()
        mock_svc.delete_task.return_value = None

        app.dependency_overrides[get_task_service] = lambda: mock_svc
        for dep in (get_note_service, get_calendar_event_service, get_transaction_service,
                    get_account_service, get_budget_service, get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "task", "command": "delete", "arguments": {"id": "7"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["result"]["deleted"] is True
            assert data["result"]["id"] == 7
        finally:
            app.dependency_overrides.clear()

    def test_note_add(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        mock_svc = AsyncMock()
        mock_svc.create_note.return_value = _note_read_mock(title="chocolate is good")

        app.dependency_overrides[get_note_service] = lambda: mock_svc
        for dep in (get_task_service, get_calendar_event_service, get_transaction_service,
                    get_account_service, get_budget_service, get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "note", "command": "add", "arguments": {"content": "chocolate is good"}},
                headers=AUTH,
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["type"] == "note"
            assert data["result"]["title"] == "chocolate is good"
        finally:
            app.dependency_overrides.clear()

    def test_task_not_found_returns_404(self, client):
        from app.dependencies import get_task_service, get_note_service, get_calendar_event_service
        from app.dependencies import get_transaction_service, get_account_service, get_budget_service, get_recurring_transaction_service
        from app.main import app

        mock_svc = AsyncMock()
        mock_svc.update_task.return_value = None

        app.dependency_overrides[get_task_service] = lambda: mock_svc
        for dep in (get_note_service, get_calendar_event_service, get_transaction_service,
                    get_account_service, get_budget_service, get_recurring_transaction_service):
            app.dependency_overrides[dep] = lambda: AsyncMock()

        try:
            response = client.post(
                "/commands/execute",
                json={"type": "task", "command": "complete", "arguments": {"id": "999"}},
                headers=AUTH,
            )
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()
