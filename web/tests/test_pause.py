import httpx


class TestPauseControl:
    def test_renders_take_a_breath_when_not_paused(self, client, mock_api):
        mock_api["get"].return_value = {"paused": False, "paused_at": None}

        resp = client.get("/pause/control")

        assert resp.status_code == 200
        assert "Take a breath" in resp.text
        mock_api["get"].assert_awaited_once_with("/core/pause")

    def test_renders_banner_when_paused(self, client, mock_api):
        mock_api["get"].return_value = {"paused": True, "paused_at": "2026-09-01T10:00:00+00:00"}

        resp = client.get("/pause/control")

        assert resp.status_code == 200
        assert "Resume" in resp.text
        assert "Paused" in resp.text


class TestStartPause:
    def test_posts_and_renders_paused_state(self, client, mock_api):
        mock_api["post"].return_value = {"paused": True, "paused_at": "2026-09-01T10:00:00+00:00"}

        resp = client.post("/pause")

        assert resp.status_code == 200
        assert "Resume" in resp.text
        mock_api["post"].assert_awaited_once_with("/core/pause")

    def test_falls_back_to_current_state_on_conflict(self, client, mock_api):
        request = httpx.Request("POST", "http://api/core/pause")
        response = httpx.Response(400, request=request, json={"detail": "Already paused"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)
        mock_api["get"].return_value = {"paused": True, "paused_at": "2026-09-01T10:00:00+00:00"}

        resp = client.post("/pause")

        assert resp.status_code == 200
        assert "Resume" in resp.text
        assert "Already paused" in resp.text
        mock_api["get"].assert_awaited_once_with("/core/pause")


class TestStopPause:
    def test_posts_and_renders_summary(self, client, mock_api):
        mock_api["post"].return_value = {
            "paused": False,
            "resumed_at": "2026-09-04T09:00:00+00:00",
            "tasks_urgency_reset": 3,
            "tasks_deadline_shifted": 1,
        }

        resp = client.post("/pause/resume")

        assert resp.status_code == 200
        assert "Take a breath" in resp.text
        assert "reset 3 task(s)" in resp.text
        assert "shifted 1 deadline(s)" in resp.text
        mock_api["post"].assert_awaited_once_with("/core/pause/resume")

    def test_falls_back_to_current_state_on_conflict(self, client, mock_api):
        request = httpx.Request("POST", "http://api/core/pause/resume")
        response = httpx.Response(400, request=request, json={"detail": "Not paused"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)
        mock_api["get"].return_value = {"paused": False, "paused_at": None}

        resp = client.post("/pause/resume")

        assert resp.status_code == 200
        assert "Take a breath" in resp.text
        assert "Not paused" in resp.text

    def test_surfaces_error_on_server_error(self, client, mock_api):
        request = httpx.Request("POST", "http://api/core/pause/resume")
        response = httpx.Response(500, request=request, json={"detail": "Internal Server Error"})
        mock_api["post"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)
        mock_api["get"].return_value = {"paused": True, "paused_at": "2026-09-14T12:11:03+00:00"}

        resp = client.post("/pause/resume")

        assert resp.status_code == 200
        assert "Resume" in resp.text
        assert "Internal Server Error" in resp.text
