import httpx


def _status(level="overloaded", overdue=7, urgent=5, streak_days=3):
    return {
        "level": level, "overdue": overdue, "urgent": urgent, "active": 20,
        "overdue_threshold": 5, "urgent_threshold": 4, "streak_days": streak_days,
    }


_SETTINGS = {
    "overload_overdue_threshold": 5, "overload_urgent_threshold": 4, "overload_max_listed": 5,
    "overload_urgent_interval_hours": 4, "overdue_grace_hours_high": 0, "overdue_grace_hours_medium": 48,
    "overdue_grace_hours_low": 168, "undated_escalation_days_high": 7, "undated_escalation_days_medium": 21,
    "undated_escalation_days_low": 45, "urgency_reset_days": 7,
}


def _http_error(status_code, detail=None):
    request = httpx.Request("PUT", "http://api/core/reminder-settings")
    response = httpx.Response(status_code, request=request, json={"detail": detail} if detail else {})
    return httpx.HTTPStatusError("error", request=request, response=response)


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


class TestSettingsForm:
    def test_renders_current_values(self, client, mock_api):
        mock_api["get"].return_value = _SETTINGS

        resp = client.get("/overload/settings")

        assert resp.status_code == 200
        assert 'name="overload_max_listed" value="5"' in resp.text
        assert 'name="overdue_grace_hours_low" value="168"' in resp.text
        assert 'name="undated_escalation_days_medium" value="21"' in resp.text
        mock_api["get"].assert_awaited_once_with("/core/reminder-settings")

    def test_load_failure_shows_a_message(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")

        resp = client.get("/overload/settings")

        assert "Could not load reminder settings" in resp.text

    def test_save_sends_integers_and_confirms(self, client, mock_api):
        mock_api["put"].return_value = {**_SETTINGS, "overload_max_listed": 8}

        resp = client.post("/overload/settings", data={**{k: str(v) for k, v in _SETTINGS.items()}, "overload_max_listed": "8"})

        assert resp.status_code == 200
        assert "Saved." in resp.text
        assert 'name="overload_max_listed" value="8"' in resp.text
        path = mock_api["put"].await_args.args[0]
        payload = mock_api["put"].await_args.kwargs["json"]
        assert path == "/core/reminder-settings"
        assert payload["overload_max_listed"] == 8
        assert all(isinstance(v, int) for v in payload.values())

    def test_blank_fields_are_not_sent(self, client, mock_api):
        mock_api["put"].return_value = _SETTINGS

        client.post("/overload/settings", data={"overload_max_listed": "6", "overload_urgent_threshold": ""})

        assert mock_api["put"].await_args.kwargs["json"] == {"overload_max_listed": 6}

    def test_non_numeric_value_is_rejected_without_calling_the_backend(self, client, mock_api):
        mock_api["get"].return_value = _SETTINGS

        resp = client.post("/overload/settings", data={"overload_max_listed": "lots"})

        assert "must be a whole number" in resp.text
        mock_api["put"].assert_not_awaited()

    def test_backend_validation_error_is_shown(self, client, mock_api):
        mock_api["put"].side_effect = _http_error(422)
        mock_api["get"].return_value = _SETTINGS

        resp = client.post("/overload/settings", data={"overload_max_listed": "0"})

        assert resp.status_code == 200
        assert "Invalid value" in resp.text
        assert "Saved." not in resp.text
