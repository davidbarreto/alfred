from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.study.generator.service import PlanGenerationError, StudyTrackNotFoundError
from app.features.study.plans.schemas import StudyPlanRead, StudyPlansOverview
from app.features.study.plans.service import ActivePlanCapReachedError, InvalidPlanTransitionError
from app.features.study.settings.schemas import StudySettingsRead
from app.features.study.tracks.schemas import StudyTrackRead

AUTH = {"Authorization": "Bearer test-api-token"}
_NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)


def _plan(status: str = "active") -> StudyPlanRead:
    return StudyPlanRead(
        id=1, track_id=1, title="Dynamic programming", goal="Solve medium DP problems", priority="medium",
        status=status, activated_at=_NOW, completed_at=None, tags=["algorithms"], items=[],
        created_at=_NOW, updated_at=_NOW,
    )


@pytest.fixture
def plan_service():
    svc = AsyncMock()
    svc.get_plans.return_value = [_plan()]
    svc.get_plan.return_value = _plan()
    svc.get_overview.return_value = StudyPlansOverview(active=[_plan()], backlog=[], max_active_plans=3)
    return svc


@pytest.fixture
def generator_service():
    svc = AsyncMock()
    svc.generate_from_cs_stats.return_value = _plan()
    return svc


@pytest.fixture
def settings_service():
    svc = AsyncMock()
    svc.get.return_value = StudySettingsRead(max_active_plans=3)
    svc.update.return_value = StudySettingsRead(max_active_plans=2)
    return svc


@pytest.fixture
def track_service():
    svc = AsyncMock()
    svc.get_tracks.return_value = [StudyTrackRead(
        id=1, name="Software Engineering", description=None, is_active=True, created_at=_NOW, updated_at=_NOW,
    )]
    return svc


@pytest.fixture
def client(plan_service, generator_service, settings_service, track_service):
    from app.dependencies import (
        get_study_plan_generator_service,
        get_study_plan_service,
        get_study_settings_service,
        get_study_track_service,
    )
    from app.main import app
    app.dependency_overrides[get_study_plan_service] = lambda: plan_service
    app.dependency_overrides[get_study_plan_generator_service] = lambda: generator_service
    app.dependency_overrides[get_study_settings_service] = lambda: settings_service
    app.dependency_overrides[get_study_track_service] = lambda: track_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestPlansRead:
    def test_list_passes_filters(self, client, plan_service):
        response = client.get("/study/plans?closed=true&limit=5", headers=AUTH)
        assert response.status_code == 200
        filters = plan_service.get_plans.call_args[0][0]
        assert filters.closed is True and filters.limit == 5

    def test_overview(self, client):
        response = client.get("/study/plans/overview", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["max_active_plans"] == 3

    def test_get_missing_plan_is_404(self, client, plan_service):
        plan_service.get_plan.return_value = None
        assert client.get("/study/plans/99", headers=AUTH).status_code == 404

    def test_requires_auth(self, client):
        assert client.get("/study/plans").status_code == 403


class TestGenerate:
    def test_returns_201(self, client):
        response = client.post("/study/plans/generate", headers=AUTH)
        assert response.status_code == 201
        assert response.json()["title"] == "Dynamic programming"

    def test_llm_failure_is_502(self, client, generator_service):
        generator_service.generate_from_cs_stats.side_effect = PlanGenerationError("bad json")
        assert client.post("/study/plans/generate", headers=AUTH).status_code == 502

    def test_missing_track_is_404(self, client, generator_service):
        generator_service.generate_from_cs_stats.side_effect = StudyTrackNotFoundError("Software Engineering")
        assert client.post("/study/plans/generate", headers=AUTH).status_code == 404


class TestTransitions:
    def test_activate_at_cap_is_409(self, client, plan_service):
        plan_service.activate_plan.side_effect = ActivePlanCapReachedError(3)
        response = client.post("/study/plans/1/activate", headers=AUTH)
        assert response.status_code == 409
        assert "3 active plan" in response.json()["detail"]

    def test_invalid_transition_is_409(self, client, plan_service):
        plan_service.complete_plan.side_effect = InvalidPlanTransitionError(1, "backlog", "complete")
        assert client.post("/study/plans/1/complete", headers=AUTH).status_code == 409

    @pytest.mark.parametrize("action", ["activate", "complete", "abandon"])
    def test_missing_plan_is_404(self, client, plan_service, action):
        getattr(plan_service, f"{action}_plan").return_value = None
        assert client.post(f"/study/plans/99/{action}", headers=AUTH).status_code == 404

    def test_abandon_returns_plan(self, client, plan_service):
        plan_service.abandon_plan.return_value = _plan(status="abandoned")
        response = client.post("/study/plans/1/abandon", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["status"] == "abandoned"


class TestDeleteAndItems:
    def test_delete_returns_204(self, client, plan_service):
        plan_service.delete_plan.return_value = True
        assert client.delete("/study/plans/1", headers=AUTH).status_code == 204

    def test_delete_missing_is_404(self, client, plan_service):
        plan_service.delete_plan.return_value = False
        assert client.delete("/study/plans/99", headers=AUTH).status_code == 404

    def test_complete_item_returns_204(self, client, plan_service):
        plan_service.mark_item_done.return_value = True
        assert client.post("/study/plans/items/5/complete", headers=AUTH).status_code == 204

    def test_complete_missing_item_is_404(self, client, plan_service):
        plan_service.mark_item_done.return_value = False
        assert client.post("/study/plans/items/99/complete", headers=AUTH).status_code == 404


class TestSettingsAndTracks:
    def test_get_settings(self, client):
        assert client.get("/study/settings", headers=AUTH).json() == {"max_active_plans": 3}

    def test_update_settings(self, client, settings_service):
        response = client.put("/study/settings", json={"max_active_plans": 2}, headers=AUTH)
        assert response.status_code == 200
        settings_service.update.assert_awaited_once()

    def test_update_settings_rejects_zero(self, client):
        assert client.put("/study/settings", json={"max_active_plans": 0}, headers=AUTH).status_code == 422

    def test_list_tracks(self, client):
        response = client.get("/study/tracks", headers=AUTH)
        assert response.status_code == 200
        assert response.json()[0]["name"] == "Software Engineering"
