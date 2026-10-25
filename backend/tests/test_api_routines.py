from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.organizer.routines.schemas import RoutineDetail, RoutineRead, RoutineStepRead
from app.features.organizer.routines.service import RoutineConflictError, RoutineValidationError

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 10, 1, 9, 0)


def _step(**overrides) -> RoutineStepRead:
    defaults = dict(
        id=1, routine_id=1, position=0, title="Leave", duration_minutes=20, anchor="start", offset_minutes=-50,
        created_at=_NOW, updated_at=_NOW,
    )
    defaults.update(overrides)
    return RoutineStepRead(**defaults)


def _routine(**overrides) -> RoutineRead:
    defaults = dict(id=1, name="Dinner", steps=[_step()], event_ids=[7], created_at=_NOW, updated_at=_NOW)
    defaults.update(overrides)
    return RoutineRead(**defaults)


@pytest.fixture
def mock_service():
    svc = AsyncMock()
    svc.get_routines.return_value = [_routine()]
    svc.get_routine.return_value = RoutineDetail(**_routine().model_dump())
    svc.create_routine.return_value = _routine(id=2)
    svc.update_routine.return_value = _routine(name="Renamed")
    svc.delete_routine.return_value = True
    svc.add_step.return_value = _step(id=5)
    svc.update_step.return_value = _step(title="Updated")
    svc.delete_step.return_value = True
    svc.attach.return_value = _routine()
    svc.detach.return_value = True
    return svc


@pytest.fixture
def client(mock_service):
    from app.main import app
    from app.dependencies import get_routine_service

    app.dependency_overrides[get_routine_service] = lambda: mock_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestListAndGet:
    def test_list(self, client, mock_service):
        response = client.get("/organizer/routines", headers=AUTH)
        assert response.status_code == 200
        body = response.json()
        assert body[0]["name"] == "Dinner"
        assert body[0]["event_ids"] == [7]
        assert body[0]["steps"][0]["offset_minutes"] == -50
        mock_service.get_routines.assert_awaited_once_with(None)

    def test_list_filters_by_active(self, client, mock_service):
        client.get("/organizer/routines?active=true", headers=AUTH)
        mock_service.get_routines.assert_awaited_once_with(True)

    def test_get(self, client):
        response = client.get("/organizer/routines/1", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["steps"][0]["checklist_note"] is None

    def test_get_unknown_is_404(self, client, mock_service):
        mock_service.get_routine.return_value = None
        assert client.get("/organizer/routines/9", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.get("/organizer/routines").status_code == 403


class TestCreateUpdateDelete:
    def test_create(self, client):
        response = client.post("/organizer/routines", json={"name": "Dinner"}, headers=AUTH)
        assert response.status_code == 201
        assert response.json()["id"] == 2

    def test_create_scheduled_requires_start_date(self, client):
        response = client.post(
            "/organizer/routines", json={"name": "Morning", "recurrence_rule": "FREQ=DAILY"}, headers=AUTH
        )
        assert response.status_code == 422

    def test_create_with_invalid_rule_is_422(self, client, mock_service):
        mock_service.create_routine.side_effect = RoutineValidationError("Invalid recurrence_rule")
        response = client.post(
            "/organizer/routines",
            json={"name": "x", "recurrence_rule": "FREQ=NOPE", "starts_on": "2026-10-01"},
            headers=AUTH,
        )
        assert response.status_code == 422
        assert "Invalid recurrence_rule" in response.json()["detail"]

    def test_update(self, client):
        response = client.patch("/organizer/routines/1", json={"name": "Renamed"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["name"] == "Renamed"

    def test_update_unknown_is_404(self, client, mock_service):
        mock_service.update_routine.return_value = None
        assert client.patch("/organizer/routines/9", json={"name": "x"}, headers=AUTH).status_code == 404

    def test_update_rule_violation_is_422(self, client, mock_service):
        mock_service.update_routine.side_effect = RoutineValidationError("detach first")
        assert client.patch("/organizer/routines/1", json={"active": False}, headers=AUTH).status_code == 422

    def test_delete(self, client):
        assert client.delete("/organizer/routines/1", headers=AUTH).status_code == 204

    def test_delete_unknown_is_404(self, client, mock_service):
        mock_service.delete_routine.return_value = False
        assert client.delete("/organizer/routines/9", headers=AUTH).status_code == 404


class TestSteps:
    def test_add_step(self, client, mock_service):
        response = client.post(
            "/organizer/routines/1/steps", json={"title": "Leave", "anchor": "start", "offset_minutes": -50}, headers=AUTH
        )
        assert response.status_code == 201
        assert response.json()["id"] == 5
        assert mock_service.add_step.call_args.args[0] == 1

    def test_add_step_needs_exactly_one_timing_form(self, client):
        response = client.post("/organizer/routines/1/steps", json={"title": "Leave"}, headers=AUTH)
        assert response.status_code == 422

    def test_add_step_to_unknown_routine_is_404(self, client, mock_service):
        mock_service.add_step.return_value = None
        response = client.post(
            "/organizer/routines/9/steps", json={"title": "x", "anchor": "end", "offset_minutes": 0}, headers=AUTH
        )
        assert response.status_code == 404

    def test_taken_position_is_409(self, client, mock_service):
        mock_service.add_step.side_effect = RoutineConflictError("taken")
        response = client.post(
            "/organizer/routines/1/steps",
            json={"title": "x", "anchor": "end", "offset_minutes": 0, "position": 0},
            headers=AUTH,
        )
        assert response.status_code == 409

    def test_wrong_form_for_routine_kind_is_422(self, client, mock_service):
        mock_service.add_step.side_effect = RoutineValidationError("needs a window")
        response = client.post(
            "/organizer/routines/1/steps", json={"title": "x", "anchor": "end", "offset_minutes": 0}, headers=AUTH
        )
        assert response.status_code == 422

    def test_update_step(self, client):
        response = client.patch("/organizer/routines/steps/5", json={"title": "Updated"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["title"] == "Updated"

    def test_update_unknown_step_is_404(self, client, mock_service):
        mock_service.update_step.return_value = None
        assert client.patch("/organizer/routines/steps/9", json={"title": "x"}, headers=AUTH).status_code == 404

    def test_delete_step(self, client):
        assert client.delete("/organizer/routines/steps/5", headers=AUTH).status_code == 204

    def test_delete_unknown_step_is_404(self, client, mock_service):
        mock_service.delete_step.return_value = False
        assert client.delete("/organizer/routines/steps/9", headers=AUTH).status_code == 404


class TestAttach:
    def test_attach(self, client, mock_service):
        response = client.post("/organizer/routines/1/events/7", headers=AUTH)
        assert response.status_code == 200
        mock_service.attach.assert_awaited_once_with(1, 7)

    def test_attach_scheduled_routine_is_422(self, client, mock_service):
        mock_service.attach.side_effect = RoutineValidationError("scheduled")
        assert client.post("/organizer/routines/1/events/7", headers=AUTH).status_code == 422

    def test_attach_unknown_routine_is_404(self, client, mock_service):
        mock_service.attach.return_value = None
        assert client.post("/organizer/routines/9/events/7", headers=AUTH).status_code == 404

    def test_detach(self, client, mock_service):
        assert client.delete("/organizer/routines/events/7", headers=AUTH).status_code == 204
        mock_service.detach.assert_awaited_once_with(7)

    def test_detach_unknown_event_is_404(self, client, mock_service):
        mock_service.detach.return_value = False
        assert client.delete("/organizer/routines/events/9", headers=AUTH).status_code == 404
