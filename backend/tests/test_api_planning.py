from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.features.planning.schemas import DayPlanRead, PlanningSettingsRead

AUTH = {"Authorization": "Bearer test-api-token"}


@pytest.fixture
def plan_service():
    svc = AsyncMock()
    svc.get_plan.return_value = DayPlanRead(
        date="2026-10-21", timezone="Europe/Lisbon", preferences={"work_target_minutes": 480}
    )
    return svc


@pytest.fixture
def settings_service():
    svc = AsyncMock()
    stored = PlanningSettingsRead(work_target_minutes=480, work_tag="work", office_tag="office")
    svc.get.return_value = stored
    svc.update.return_value = stored.model_copy(update={"wake_time": "07:30"})
    return svc


@pytest.fixture
def client(plan_service, settings_service):
    from app.main import app
    from app.dependencies import get_day_plan_service, get_planning_settings_service

    app.dependency_overrides[get_day_plan_service] = lambda: plan_service
    app.dependency_overrides[get_planning_settings_service] = lambda: settings_service
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestDayRoute:
    def test_defaults(self, client, plan_service):
        response = client.get("/planning/day", headers=AUTH)
        assert response.status_code == 200
        assert response.json()["timezone"] == "Europe/Lisbon"
        plan_service.get_plan.assert_awaited_once_with(None, 1, None)

    def test_null_fields_are_omitted(self, client):
        body = client.get("/planning/day", headers=AUTH).json()
        assert "timeline" not in body and "study" not in body and "office" not in body

    def test_query_arguments(self, client, plan_service):
        from datetime import date

        client.get("/planning/day?date=2026-10-26&days=7&work_minutes=0", headers=AUTH)
        plan_service.get_plan.assert_awaited_once_with(date(2026, 10, 26), 7, 0)

    @pytest.mark.parametrize("query", ["days=0", "days=8", "work_minutes=-1", "date=tomorrow"])
    def test_invalid_query_is_422(self, client, query):
        assert client.get(f"/planning/day?{query}", headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/planning/day").status_code == 403


class TestSettingsRoutes:
    def test_get(self, client):
        body = client.get("/planning/settings", headers=AUTH).json()
        assert body["work_target_minutes"] == 480 and body["work_tag"] == "work"

    def test_put_updates_only_given_fields(self, client, settings_service):
        response = client.put("/planning/settings", json={"wake_time": "07:30"}, headers=AUTH)
        assert response.status_code == 200
        assert response.json()["wake_time"] == "07:30"
        assert settings_service.update.call_args.args[0].model_dump(exclude_unset=True) == {"wake_time": "07:30"}

    def test_put_with_explicit_null_resets(self, client, settings_service):
        client.put("/planning/settings", json={"office_days_per_week": None}, headers=AUTH)
        assert settings_service.update.call_args.args[0].model_dump(exclude_unset=True) == {"office_days_per_week": None}

    @pytest.mark.parametrize("body", [{"wake_time": "7am"}, {"office_days_per_week": 9}, {"preferred_work_windows": ["x"]}])
    def test_invalid_body_is_422(self, client, body):
        assert client.put("/planning/settings", json=body, headers=AUTH).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/planning/settings").status_code == 403
