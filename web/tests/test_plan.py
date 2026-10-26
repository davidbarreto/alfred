from datetime import date

import httpx
import pytest


def _plan(plan_date="2026-10-21", version=2, notes="Light day", items=None, id=1, archived_at=None):
    return {
        "id": id, "plan_date": plan_date, "version": version, "notes": notes, "source": "mcp",
        "created_at": "2026-10-20T20:00:00Z", "updated_at": "2026-10-20T20:00:00Z", "archived_at": archived_at,
        "items": items if items is not None else [
            {"start": "2026-10-21T09:00:00+01:00", "end": "2026-10-21T10:30:00+01:00", "kind": "task", "ref_id": 4,
             "title": "Write the report", "note": "Before standup"},
            {"start": "2026-10-21T18:00:00+01:00", "end": "2026-10-21T18:40:00+01:00", "kind": "routine_step", "ref_id": 101,
             "title": "Prepare dinner", "note": None},
        ],
    }


def _settings(**kw):
    base = {"wake_time": "07:30", "sleep_time": None, "work_target_minutes": 480, "preferred_work_windows": ["10:00-14:00"],
            "workdays": ["mon", "tue", "wed", "thu", "fri"], "work_tag": "work", "office_tag": "office", "office_days_per_week": 4, "office_min_minutes": 0}
    base.update(kw)
    return base


def _routes(saved=None, history=None, settings=None):
    def fake_get(path, params=None):
        if path == "/planning/saved":
            return saved if saved is not None else []
        if path == "/planning/saved/history":
            return history if history is not None else []
        if path == "/planning/settings":
            return settings
        raise AssertionError(path)

    return fake_get


@pytest.fixture
def wednesday(monkeypatch):
    monkeypatch.setattr("app.routes.plan.local_today", lambda: date(2026, 10, 21))


@pytest.mark.usefixtures("wednesday")
class TestPlanPage:
    def test_shows_blocks_with_times_notes_and_version(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan()], [_plan(version=2), _plan(version=1)], _settings())

        resp = client.get("/plan?date=2026-10-21")

        text = resp.text
        assert resp.status_code == 200
        assert "Wednesday 21 October 2026" in text
        assert "09:00–10:30" in text and "Write the report" in text and "Before standup" in text
        assert "18:00–18:40" in text and "Prepare dinner" in text
        assert "Light day" in text
        assert "Version 2" in text and "Version 1" in text

    def test_block_icon_follows_its_kind(self, client, mock_api):
        items = [
            {"start": "2026-10-21T19:00:00+01:00", "end": "2026-10-21T20:00:00+01:00", "kind": "meal", "ref_id": None, "title": "Dinner", "note": None},
            {"start": "2026-10-21T16:00:00+01:00", "end": "2026-10-21T16:15:00+01:00", "kind": "break", "ref_id": None, "title": "Rest", "note": None},
        ]
        mock_api["get"].side_effect = _routes([_plan(items=items)], [_plan(items=items)], _settings())

        text = client.get("/plan?date=2026-10-21").text

        assert "ti-tools-kitchen-2" in text and "ti-coffee" in text

    def test_defaults_to_today(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], [], _settings())
        client.get("/plan")
        saved_call = next(c for c in mock_api["get"].await_args_list if c.args[0] == "/planning/saved")
        assert saved_call.kwargs["params"] == {"from": "2026-10-19", "to": "2026-10-25"}

    def test_invalid_date_falls_back_to_today(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], [], _settings())
        assert "Wednesday 21 October 2026" in client.get("/plan?date=nonsense").text

    def test_week_strip_marks_days_that_have_a_plan(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan("2026-10-21"), _plan("2026-10-23")], [], _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert text.count("rounded-full bg-[#639922]") == 2
        assert 'href="/plan?date=2026-10-19"' in text and 'href="/plan?date=2026-10-25"' in text

    def test_day_navigation(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], [], _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert 'href="/plan?date=2026-10-20"' in text and 'href="/plan?date=2026-10-22"' in text

    def test_empty_day_message(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], [], _settings())
        assert "No plan saved for this day" in client.get("/plan?date=2026-10-21").text

    def test_plan_saved_empty(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan(items=[], notes="Day off")], [_plan()], _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert "This day was saved empty" in text and "Day off" in text

    def test_page_has_no_edit_form(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan()], [_plan()], _settings())
        text = client.get("/plan?date=2026-10-21").text.split('id="planning-settings"')[0]
        assert "<form" not in text.split('id="saved-plan"')[1]

    def test_active_version_offers_archive_and_delete(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan(id=5)], [_plan(id=5)], _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert 'data-plan-action="archive" data-plan-id="5"' in text
        assert 'data-plan-action="delete" data-plan-id="5"' in text
        assert 'data-plan-action="restore"' not in text

    def test_versions_are_listed_with_links(self, client, mock_api):
        history = [_plan(id=2, version=2), _plan(id=1, version=1, archived_at="2026-10-20T21:00:00Z", items=[])]
        mock_api["get"].side_effect = _routes([history[0]], history, _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert 'id="plan-versions"' in text
        assert "/plan?date=2026-10-21&version=1" in text and "/plan?date=2026-10-21&version=2" in text
        assert "0 blocks" in text and "2 blocks" in text and "archived" in text

    def test_single_version_has_no_versions_list(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_plan()], [_plan()], _settings())
        assert 'id="plan-versions"' not in client.get("/plan?date=2026-10-21").text

    def test_an_older_version_can_be_viewed_and_restored(self, client, mock_api):
        old = _plan(id=1, version=1, notes="First draft", archived_at="2026-10-20T21:00:00Z", items=[])
        mock_api["get"].side_effect = _routes([_plan(id=2)], [_plan(id=2), old], _settings())
        text = client.get("/plan?date=2026-10-21&version=1").text
        assert "Version 1 (archived)" in text and "First draft" in text
        assert "Write the report" not in text.split('id="plan-versions"')[0]
        assert 'data-plan-action="restore" data-plan-id="1"' in text
        assert 'data-plan-action="archive"' not in text

    @pytest.mark.parametrize("version", ["9", "abc"])
    def test_unknown_version_falls_back_to_the_active_plan(self, client, mock_api, version):
        mock_api["get"].side_effect = _routes([_plan(id=2)], [_plan(id=2)], _settings())
        assert "Version 2" in client.get(f"/plan?date=2026-10-21&version={version}").text

    def test_day_with_only_archived_versions_lists_them(self, client, mock_api):
        old = _plan(id=1, version=1, archived_at="2026-10-20T21:00:00Z")
        mock_api["get"].side_effect = _routes([], [old], _settings())
        text = client.get("/plan?date=2026-10-21").text
        assert "every saved version is archived" in text
        assert 'id="plan-versions"' in text and "version=1" in text

    def test_settings_form_is_prefilled(self, client, mock_api):
        mock_api["get"].side_effect = _routes([], [], _settings())
        text = client.get("/plan").text
        assert 'name="wake_time" type="time" value="07:30"' in text
        assert 'value="10:00-14:00"' in text
        assert 'name="workdays" value="mon, tue, wed, thu, fri"' in text
        assert 'name="office_days_per_week" type="number" min="1" max="7" value="4"' in text

    def test_unreachable_backend_still_renders(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        resp = client.get("/plan")
        assert resp.status_code == 200 and "unavailable" in resp.text

    def test_requires_authentication(self, anon_client):
        assert anon_client.get("/plan", follow_redirects=False).status_code == 302


class TestPlanVersionWrites:
    def test_archive_is_forwarded(self, client, mock_api):
        mock_api["post"].return_value = _plan()
        assert client.post("/plan/saved/3/archive").status_code == 200
        mock_api["post"].assert_awaited_once_with("/planning/saved/3/archive")

    def test_restore_is_forwarded(self, client, mock_api):
        mock_api["post"].return_value = _plan()
        assert client.post("/plan/saved/3/restore").status_code == 200
        mock_api["post"].assert_awaited_once_with("/planning/saved/3/restore")

    def test_delete_is_forwarded(self, client, mock_api):
        mock_api["delete"].return_value = None
        assert client.delete("/plan/saved/3").status_code == 200
        mock_api["delete"].assert_awaited_once_with("/planning/saved/3")

    def test_backend_message_is_relayed(self, client, mock_api):
        request = httpx.Request("POST", "http://api/x")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "conflict", request=request, response=httpx.Response(409, json={"detail": "This version is already archived"}, request=request)
        )
        resp = client.post("/plan/saved/3/archive")
        assert resp.status_code == 409 and resp.json() == {"error": "This version is already archived"}


class TestSettingsWrite:
    def test_put_is_forwarded(self, client, mock_api):
        mock_api["put"].return_value = _settings()
        body = {"wake_time": "07:30", "office_days_per_week": None, "preferred_work_windows": []}
        resp = client.put("/plan/settings", json=body)
        assert resp.status_code == 200
        mock_api["put"].assert_awaited_once_with("/planning/settings", json=body)

    def test_validation_message_is_relayed(self, client, mock_api):
        request = httpx.Request("PUT", "http://api/x")
        mock_api["put"].side_effect = httpx.HTTPStatusError(
            "bad", request=request, response=httpx.Response(422, json={"detail": "bad time"}, request=request)
        )
        resp = client.put("/plan/settings", json={"wake_time": "7am"})
        assert resp.status_code == 422 and resp.json() == {"error": "bad time"}
