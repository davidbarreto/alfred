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


class TestSavedRoutes:
    @pytest.fixture
    def saved_service(self):
        from datetime import date, datetime, timezone

        from app.features.planning.saved_plans.schemas import SavedDayPlanRead

        now = datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc)
        plan = SavedDayPlanRead(
            id=1, plan_date=date(2026, 10, 21), version=1, items=[], notes="n", source="mcp",
            created_at=now, updated_at=now,
        )
        svc = AsyncMock()
        svc.save.return_value = [plan]
        svc.get_saved.return_value = [plan]
        svc.get_history.return_value = [plan]
        svc.archive.return_value = plan
        svc.restore.return_value = plan
        return svc

    @pytest.fixture
    def saved_client(self, client, saved_service):
        from app.main import app
        from app.dependencies import get_saved_plan_service

        app.dependency_overrides[get_saved_plan_service] = lambda: saved_service
        return client

    _BODY = {"days": [{"date": "2026-10-21", "notes": "n", "items": [
        {"start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:00:00+01:00", "kind": "task", "ref_id": 4, "title": "Write"},
    ]}]}

    def test_save(self, saved_client, saved_service):
        response = saved_client.post("/planning/saved", json=self._BODY, headers=AUTH)
        assert response.status_code == 201
        assert response.json()[0]["version"] == 1
        assert saved_service.save.call_args.args[1] == "mcp"

    def test_web_client_saves_as_portal(self, saved_client, saved_service):
        saved_client.post("/planning/saved", json=self._BODY, headers={**AUTH, "X-Alfred-Client": "web"})
        assert saved_service.save.call_args.args[1] == "portal"

    def test_naive_datetime_is_422(self, saved_client):
        body = {"days": [{"date": "2026-10-21", "items": [
            {"start": "2026-10-21T09:00:00", "end": "2026-10-21T10:00:00", "kind": "break", "title": "Rest"},
        ]}]}
        assert saved_client.post("/planning/saved", json=body, headers=AUTH).status_code == 422

    def test_invalid_ref_id_is_422(self, saved_client, saved_service):
        from app.features.planning.saved_plans.service import SavedPlanValidationError

        saved_service.save.side_effect = SavedPlanValidationError("Unknown task ref_id(s): 999")
        response = saved_client.post("/planning/saved", json=self._BODY, headers=AUTH)
        assert response.status_code == 422 and "999" in response.json()["detail"]

    def test_archive(self, saved_client, saved_service):
        response = saved_client.post("/planning/saved/1/archive", headers=AUTH)
        assert response.status_code == 200
        saved_service.archive.assert_awaited_once_with(1)

    def test_restore(self, saved_client, saved_service):
        response = saved_client.post("/planning/saved/1/restore", headers=AUTH)
        assert response.status_code == 200
        saved_service.restore.assert_awaited_once_with(1)

    def test_mark_and_unmark_block_missed(self, saved_client, saved_service):
        saved_service.set_block_missed.return_value = saved_service.archive.return_value
        assert saved_client.post("/planning/saved/1/blocks/2/missed", headers=AUTH).status_code == 200
        assert saved_client.delete("/planning/saved/1/blocks/2/missed", headers=AUTH).status_code == 200
        assert [c.args for c in saved_service.set_block_missed.await_args_list] == [(1, 2, True), (1, 2, False)]

    def test_missed_unknown_block_is_404(self, saved_client, saved_service):
        from app.features.planning.saved_plans.service import SavedPlanNotFoundError

        saved_service.set_block_missed.side_effect = SavedPlanNotFoundError("no block")
        assert saved_client.post("/planning/saved/1/blocks/9/missed", headers=AUTH).status_code == 404

    def test_delete_is_204(self, saved_client, saved_service):
        response = saved_client.delete("/planning/saved/1", headers=AUTH)
        assert response.status_code == 204
        saved_service.delete.assert_awaited_once_with(1)

    @pytest.mark.parametrize("method,path,action", [
        ("post", "/planning/saved/9/archive", "archive"),
        ("post", "/planning/saved/9/restore", "restore"),
        ("delete", "/planning/saved/9", "delete"),
    ])
    def test_unknown_plan_is_404(self, saved_client, saved_service, method, path, action):
        from app.features.planning.saved_plans.service import SavedPlanNotFoundError

        getattr(saved_service, action).side_effect = SavedPlanNotFoundError("Saved plan 9 not found")
        assert getattr(saved_client, method)(path, headers=AUTH).status_code == 404

    @pytest.mark.parametrize("path,action", [("/planning/saved/1/archive", "archive"), ("/planning/saved/1/restore", "restore")])
    def test_wrong_state_is_409(self, saved_client, saved_service, path, action):
        from app.features.planning.saved_plans.service import SavedPlanConflictError

        getattr(saved_service, action).side_effect = SavedPlanConflictError("already")
        assert saved_client.post(path, headers=AUTH).status_code == 409

    def test_concurrent_save_is_409(self, saved_client, saved_service):
        from app.features.planning.saved_plans.service import SavedPlanConflictError

        saved_service.save.side_effect = SavedPlanConflictError("race")
        assert saved_client.post("/planning/saved", json=self._BODY, headers=AUTH).status_code == 409

    def test_get_saved_range(self, saved_client, saved_service):
        from datetime import date

        response = saved_client.get("/planning/saved?from=2026-10-19&to=2026-10-25", headers=AUTH)
        assert response.status_code == 200
        saved_service.get_saved.assert_awaited_once_with(date(2026, 10, 19), date(2026, 10, 25), None)

    def test_get_saved_version(self, saved_client, saved_service):
        from datetime import date

        saved_client.get("/planning/saved?from=2026-10-21&to=2026-10-21&version=2", headers=AUTH)
        saved_service.get_saved.assert_awaited_once_with(date(2026, 10, 21), date(2026, 10, 21), 2)

    def test_get_saved_requires_the_range(self, saved_client):
        assert saved_client.get("/planning/saved?from=2026-10-19", headers=AUTH).status_code == 422

    def test_range_error_is_422(self, saved_client, saved_service):
        from app.features.planning.saved_plans.service import SavedPlanValidationError

        saved_service.get_saved.side_effect = SavedPlanValidationError("too long")
        assert saved_client.get("/planning/saved?from=2026-01-01&to=2026-12-31", headers=AUTH).status_code == 422

    def test_history_is_not_shadowed_by_the_range_route(self, saved_client, saved_service):
        from datetime import date

        response = saved_client.get("/planning/saved/history?date=2026-10-21", headers=AUTH)
        assert response.status_code == 200
        saved_service.get_history.assert_awaited_once_with(date(2026, 10, 21))

    def test_requires_auth(self, saved_client):
        assert saved_client.get("/planning/saved?from=2026-10-19&to=2026-10-25").status_code == 403
