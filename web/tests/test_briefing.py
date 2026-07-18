import httpx


class TestBriefingPage:
    def test_renders_briefing_data(self, client, mock_api):
        mock_api["get"].return_value = {
            "date": "2026-07-08",
            "lookahead_days": 3,
            "weather": {
                "temperature_max_c": 24.4,
                "temperature_min_c": 15.1,
                "feels_like_max_c": 23.0,
                "precipitation_probability": 10,
                "wind_speed_max_kmh": 12.3,
                "description": "Partly cloudy",
                "advice": ["Bring a light jacket"],
            },
            "tasks": [{"title": "Ship the feature", "is_today": True, "is_overdue": False,
                       "urgency": "URGENT", "priority": "HIGH", "deadline": None}],
            "events": [],
            "birthdays": [],
            "holidays": [],
        }

        resp = client.get("/briefing/")

        assert resp.status_code == 200
        assert "2026-07-08" in resp.text
        assert "Partly cloudy" in resp.text
        assert "Ship the feature" in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/morning")

    def test_renders_empty_state_when_no_briefing_data(self, client, mock_api):
        mock_api["get"].return_value = {}

        resp = client.get("/briefing/")

        assert resp.status_code == 200
        assert "No briefing data available." in resp.text

    def test_renders_api_error_on_http_status_error(self, client, mock_api):
        request = httpx.Request("GET", "http://api/briefing/morning")
        response = httpx.Response(500, request=request, text="boom")
        mock_api["get"].side_effect = httpx.HTTPStatusError("error", request=request, response=response)

        resp = client.get("/briefing/")

        assert resp.status_code == 200
        assert "API error 500" in resp.text
        assert "No briefing data available." not in resp.text

    def test_renders_api_error_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/briefing/morning")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/briefing/")

        assert resp.status_code == 200
        assert "Cannot reach backend" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/briefing/", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestBriefingFormattedFragment:
    def test_renders_formatted_text(self, client, mock_api):
        mock_api["get"].return_value = {"text": "Good morning! Here's your day."}

        resp = client.get("/briefing/formatted")

        assert resp.status_code == 200
        assert "Good morning! Here&#39;s your day." in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/morning/formatted", params={"force": False})

    def test_forwards_force_flag_to_bypass_cache(self, client, mock_api):
        mock_api["get"].return_value = {"text": "Freshly generated briefing."}

        resp = client.get("/briefing/formatted?force=true")

        assert resp.status_code == 200
        assert "Freshly generated briefing." in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/morning/formatted", params={"force": True})

    def test_renders_fallback_message_on_http_error(self, client, mock_api):
        request = httpx.Request("GET", "http://api/briefing/morning/formatted")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/briefing/formatted")

        assert resp.status_code == 200
        assert "Could not generate formatted briefing." in resp.text


class TestEveningDigestPage:
    def test_renders_digest_data(self, client, mock_api):
        mock_api["get"].return_value = {
            "date": "2026-07-18",
            "wins": [{"title": "Paid rent"}],
            "tasks": [],
            "tomorrow_events": [],
            "notes": [],
        }

        resp = client.get("/briefing/evening")

        assert resp.status_code == 200
        assert "2026-07-18" in resp.text
        assert "Paid rent" in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/evening")

    def test_renders_empty_wins_message(self, client, mock_api):
        mock_api["get"].return_value = {
            "date": "2026-07-18", "wins": [], "tasks": [], "tomorrow_events": [], "notes": [],
        }

        resp = client.get("/briefing/evening")

        assert resp.status_code == 200
        assert "Nothing marked done today yet." in resp.text

    def test_renders_empty_state_when_no_digest_data(self, client, mock_api):
        mock_api["get"].return_value = {}

        resp = client.get("/briefing/evening")

        assert resp.status_code == 200
        assert "No digest data available." in resp.text

    def test_renders_api_error_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/briefing/evening")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/briefing/evening")

        assert resp.status_code == 200
        assert "Cannot reach backend" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/briefing/evening", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestEveningDigestFormattedFragment:
    def test_renders_formatted_text(self, client, mock_api):
        mock_api["get"].return_value = {"text": "Nice work today. Tomorrow, start with the report."}

        resp = client.get("/briefing/evening/formatted")

        assert resp.status_code == 200
        assert "Nice work today." in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/evening/formatted", params={"force": False})

    def test_forwards_force_flag_to_bypass_cache(self, client, mock_api):
        mock_api["get"].return_value = {"text": "Freshly generated digest."}

        resp = client.get("/briefing/evening/formatted?force=true")

        assert resp.status_code == 200
        assert "Freshly generated digest." in resp.text
        mock_api["get"].assert_awaited_once_with("/briefing/evening/formatted", params={"force": True})

    def test_renders_fallback_message_on_http_error(self, client, mock_api):
        request = httpx.Request("GET", "http://api/briefing/evening/formatted")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/briefing/evening/formatted")

        assert resp.status_code == 200
        assert "Could not generate formatted briefing." in resp.text
