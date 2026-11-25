import httpx


def _status(level="overloaded", overdue=7, urgent=5, streak_days=3):
    return {
        "level": level, "overdue": overdue, "urgent": urgent, "active": 20,
        "overdue_threshold": 5, "urgent_threshold": 4, "streak_days": streak_days,
    }


class TestBanner:
    def test_overloaded_banner_shows_counts_and_streak(self, client, mock_api):
        mock_api["get"].return_value = _status()

        resp = client.get("/overload/banner")

        assert resp.status_code == 200
        assert "You're overloaded" in resp.text
        assert "7 overdue, 5 urgent" in resp.text
        assert "day 3 in a row" in resp.text
        assert "Reset urgency" in resp.text
        mock_api["get"].assert_awaited_once_with("/core/overload/status")

    def test_first_overloaded_day_has_no_streak_note(self, client, mock_api):
        mock_api["get"].return_value = _status(streak_days=1)

        resp = client.get("/overload/banner")

        assert "in a row" not in resp.text

    def test_elevated_banner_is_a_soft_warning(self, client, mock_api):
        mock_api["get"].return_value = _status(level="elevated", overdue=3, urgent=1, streak_days=0)

        resp = client.get("/overload/banner")

        assert "Backlog building up: 3 overdue, 1 urgent" in resp.text
        assert "You're overloaded" not in resp.text
        assert "Reset urgency" not in resp.text

    def test_nothing_is_rendered_when_ok(self, client, mock_api):
        mock_api["get"].return_value = _status(level="ok", overdue=0, urgent=0, streak_days=0)

        resp = client.get("/overload/banner")

        assert resp.status_code == 200
        assert resp.text.strip() == ""

    def test_backend_failure_renders_nothing(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")

        resp = client.get("/overload/banner")

        assert resp.status_code == 200
        assert resp.text.strip() == ""


class TestBannerPlacement:
    def test_tasks_page_loads_the_banner(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/tasks")

        assert 'hx-get="/overload/banner"' in resp.text

    def test_dashboard_loads_the_banner(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/")

        assert 'hx-get="/overload/banner"' in resp.text


class TestReset:
    def test_resets_urgency_and_asks_htmx_to_refresh(self, client, mock_api):
        mock_api["post"].return_value = {"days": 7, "tasks_urgency_reset": 3, "tasks_deadline_moved": 2, "tasks_snoozed": 1}

        resp = client.post("/overload/reset")

        assert resp.status_code == 200
        assert resp.headers["HX-Refresh"] == "true"
        mock_api["post"].assert_awaited_once_with("/core/urgency-reset")

    def test_backend_failure_returns_422(self, client, mock_api):
        mock_api["post"].side_effect = httpx.ConnectError("down")

        resp = client.post("/overload/reset")

        assert resp.status_code == 422
        assert "HX-Refresh" not in resp.headers


def _plan(spread=True, drop=True, habits=True):
    suggestions = []
    if spread:
        suggestions.append({
            "kind": "spread", "title": "Spread 2 overdue tasks over the next days",
            "detail": "At most 3 due per day.", "applicable": True, "command": "/catchupapply spread", "tasks": [],
            "moves": [
                {"task_id": 5, "title": "Call plumber", "priority": "MEDIUM",
                 "old_deadline": "2026-10-01T09:00:00", "new_deadline": "2026-10-24T09:00:00"},
                {"task_id": 6, "title": "Fix bike", "priority": "LOW",
                 "old_deadline": "2026-10-02T09:00:00", "new_deadline": "2026-10-24T09:00:00"},
            ],
        })
    if drop:
        suggestions.append({
            "kind": "drop", "title": "Drop 2 stale task(s)?", "detail": "Cancels them.", "applicable": True,
            "command": "/catchupapply drop 7,8", "moves": [],
            "tasks": [
                {"id": 7, "title": "Old idea", "priority": "LOW", "urgency": "NORMAL", "deadline": None, "days_overdue": 50},
                {"id": 8, "title": "Other idea", "priority": "MEDIUM", "urgency": "URGENT", "deadline": None, "days_overdue": None},
            ],
        })
    if habits:
        suggestions.append({
            "kind": "habits", "title": "1 habit(s) you keep missing", "detail": "Consider dropping.",
            "applicable": False, "command": None, "moves": [],
            "tasks": [{"id": 9, "title": "Stretch", "priority": "LOW", "urgency": "NORMAL", "deadline": None, "days_overdue": None}],
        })
    return {
        "today_top": [{"id": 1, "title": "Pay invoice", "priority": "HIGH", "urgency": "URGENT",
                       "deadline": "2026-10-20T09:00:00", "days_overdue": 3}],
        "suggestions": suggestions,
    }


class TestCatchupPanel:
    def test_renders_focus_spread_drop_and_habits(self, client, mock_api):
        mock_api["get"].return_value = _plan()

        resp = client.get("/overload/catchup")

        assert resp.status_code == 200
        assert "Catch-up plan" in resp.text
        assert "Pay invoice" in resp.text and "overdue 3d" in resp.text
        assert "Spread 2 overdue tasks" in resp.text
        assert "Call plumber" in resp.text
        assert "Thu 01 Oct" in resp.text and "Sat 24 Oct" in resp.text
        assert "Apply plan" in resp.text
        assert 'name="task_ids" value="7"' in resp.text
        assert 'name="task_ids" value="8"' in resp.text
        assert "Drop selected" in resp.text
        assert "Stretch" in resp.text
        mock_api["get"].assert_awaited_once_with("/core/catchup")

    def test_empty_plan_shows_a_message(self, client, mock_api):
        mock_api["get"].return_value = {"today_top": [], "suggestions": []}

        resp = client.get("/overload/catchup")

        assert "Nothing to catch up on" in resp.text

    def test_backend_failure_shows_a_message(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")

        resp = client.get("/overload/catchup")

        assert "Could not load the catch-up plan" in resp.text

    def test_banner_offers_the_catch_up_plan(self, client, mock_api):
        mock_api["get"].return_value = _status()

        resp = client.get("/overload/banner")

        assert 'hx-get="/overload/catchup"' in resp.text
        assert 'hx-target="#catchup-panel"' in resp.text

    def test_pages_host_the_panel_and_refresh_the_banner_after_applying(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/tasks")

        assert 'id="catchup-panel"' in resp.text
        assert "catchup-applied from:body" in resp.text


class TestApplyCatchup:
    def test_spread_posts_and_reports_the_result(self, client, mock_api):
        mock_api["post"].return_value = {"kind": "spread", "applied": 4, "skipped": 0}
        mock_api["get"].return_value = {"today_top": [], "suggestions": []}

        resp = client.post("/overload/catchup/apply", data={"kind": "spread"})

        assert resp.status_code == 200
        assert "Moved 4 task(s)." in resp.text
        assert resp.headers["HX-Trigger"] == "catchup-applied"
        mock_api["post"].assert_awaited_once_with("/core/catchup/apply", json={"kind": "spread"})

    def test_drop_sends_the_selected_ids(self, client, mock_api):
        mock_api["post"].return_value = {"kind": "drop", "applied": 1, "skipped": 1}
        mock_api["get"].return_value = {"today_top": [], "suggestions": []}

        resp = client.post("/overload/catchup/apply", data={"kind": "drop", "task_ids": ["7", "8"]})

        assert "Dropped 1 task(s)." in resp.text
        assert "1 no longer qualified" in resp.text
        mock_api["post"].assert_awaited_once_with("/core/catchup/apply", json={"kind": "drop", "task_ids": [7, 8]})

    def test_drop_with_nothing_selected_never_calls_the_backend(self, client, mock_api):
        mock_api["get"].return_value = _plan()

        resp = client.post("/overload/catchup/apply", data={"kind": "drop"})

        assert "Select at least one task to drop." in resp.text
        mock_api["post"].assert_not_awaited()

    def test_backend_rejection_is_shown_and_the_plan_reloaded(self, client, mock_api):
        request = httpx.Request("POST", "http://api/core/catchup/apply")
        response = httpx.Response(404, request=request, json={"detail": "Nothing to spread"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)
        mock_api["get"].return_value = {"today_top": [], "suggestions": []}

        resp = client.post("/overload/catchup/apply", data={"kind": "spread"})

        assert "Nothing to spread" in resp.text
        assert "HX-Trigger" not in resp.headers
