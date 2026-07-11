import httpx


def _watcher(id=1, name="Concert tickets", enabled=True, type="html_static"):
    return {
        "id": id, "name": name, "description": None, "enabled": enabled, "type": type,
        "url": "https://example.com", "selector": ".status", "json_path": None,
        "target": "Available", "case_sensitive": True, "timeout": 10,
        "page_size": 32, "max_pages": None, "request_delay": 0, "wait_selector": None,
    }


def _execution(id=1, config_id=1, status="not_found"):
    return {
        "id": id, "config_id": config_id, "status": status, "result": None, "error": None,
        "config_snapshot": {}, "created_at": "2026-07-10T08:00:00",
    }


def _alert(id=1, status="pending"):
    return {"id": id, "execution_id": 1, "status": status, "created_at": "2026-07-10T08:00:00", "resolved_at": None}


class TestWatcherPage:
    def test_renders_monitors_charts_and_alerts(self, client, mock_api):
        mock_api["get"].side_effect = [
            [_watcher()],
            [_execution(status="found")],
            [_alert(status="pending")],
        ]

        resp = client.get("/watcher/")

        assert resp.status_code == 200
        assert "Concert tickets" in resp.text
        assert "chart-status" in resp.text
        assert "chart-time" in resp.text
        assert "pending" in resp.text
        mock_api["get"].assert_any_await("/watcher/configs", params={"limit": 200})
        mock_api["get"].assert_any_await("/watcher/executions", params={"limit": 200})
        mock_api["get"].assert_any_await("/watcher/alerts", params={"limit": 20})

    def test_renders_empty_state_when_no_monitors(self, client, mock_api):
        mock_api["get"].side_effect = [[], [], []]

        resp = client.get("/watcher/")

        assert resp.status_code == 200
        assert "No watchers yet." in resp.text

    def test_renders_error_banner_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/monitoring/configs")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/watcher/")

        assert resp.status_code == 200
        assert "Backend error" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/watcher/", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestCreateWatcher:
    def test_creates_monitor_and_renders_updated_list(self, client, mock_api):
        mock_api["post"].return_value = _watcher()
        mock_api["get"].side_effect = [[_watcher()], []]

        resp = client.post("/watcher/", data={
            "name": "Concert tickets",
            "type": "html_static",
            "url": "https://example.com",
            "target": "Available",
            "selector": ".status",
            "enabled": "on",
            "case_sensitive": "on",
            "timeout": "10",
        })

        assert resp.status_code == 200
        assert "Concert tickets" in resp.text
        mock_api["post"].assert_awaited_once_with("/watcher/configs", json={
            "name": "Concert tickets",
            "type": "html_static",
            "url": "https://example.com",
            "target": "Available",
            "enabled": True,
            "case_sensitive": True,
            "timeout": 10,
            "selector": ".status",
        })

    def test_returns_422_when_backend_create_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/monitoring/configs")
        mock_api["post"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.post("/watcher/", data={
            "name": "Concert tickets", "type": "html_static",
            "url": "https://example.com", "target": "Available",
        })

        assert resp.status_code == 422


class TestDeleteWatcher:
    def test_deletes_monitor_and_renders_updated_list(self, client, mock_api):
        mock_api["get"].side_effect = [[], []]

        resp = client.delete("/watcher/1")

        assert resp.status_code == 200
        assert "No watchers yet." in resp.text
        mock_api["delete"].assert_awaited_once_with("/watcher/configs/1")


class TestToggleWatcher:
    def test_toggles_enabled_state(self, client, mock_api):
        mock_api["get"].side_effect = [[_watcher(enabled=False)], []]

        resp = client.patch("/watcher/1/toggle", data={"enabled": "false"})

        assert resp.status_code == 200
        mock_api["patch"].assert_awaited_once_with("/watcher/configs/1", json={"enabled": False})


class TestRunWatcher:
    def test_runs_single_monitor(self, client, mock_api):
        mock_api["get"].side_effect = [[_watcher()], [_execution(status="found")]]

        resp = client.post("/watcher/1/run")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/watcher/configs/1/run")

    def test_runs_all_due_monitors(self, client, mock_api):
        mock_api["get"].side_effect = [[_watcher()], []]

        resp = client.post("/watcher/run")

        assert resp.status_code == 200
        mock_api["post"].assert_awaited_once_with("/watcher/configs/run")


class TestWatcherExecutions:
    def test_renders_execution_history(self, client, mock_api):
        mock_api["get"].return_value = [_execution(status="error")]

        resp = client.get("/watcher/1/executions")

        assert resp.status_code == 200
        assert "error" in resp.text
        mock_api["get"].assert_awaited_once_with("/watcher/configs/1/executions", params={"limit": 20})
