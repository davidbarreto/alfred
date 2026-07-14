import httpx


def _event(id=1, title="Marriage Anniversary", start="2026-07-14T00:00:00", end="2026-07-14T23:59:59", all_day=False, location=None, tags=None):
    return {
        "id": id, "title": title, "description": None, "location": location,
        "start_datetime": start, "end_datetime": end, "all_day": all_day,
        "host": None, "invitees": [], "tags": tags or [], "recurrence_rule": None,
    }


class TestCalendarPage:
    def test_renders_all_day_event_without_time_prefix(self, client, mock_api):
        mock_api["get"].return_value = [_event(all_day=True)]

        resp = client.get("/calendar?year=2026&month=7")

        assert resp.status_code == 200
        assert "Marriage Anniversary" in resp.text
        assert "00:00 Marriage Anniversary" not in resp.text

    def test_renders_overflow_indicator_for_many_events(self, client, mock_api):
        mock_api["get"].return_value = [
            _event(id=i, title=f"Event {i}", start=f"2026-07-14T0{i}:00:00", end=f"2026-07-14T0{i}:30:00")
            for i in range(5)
        ]

        resp = client.get("/calendar?year=2026&month=7")

        assert resp.status_code == 200
        assert "+2 more" in resp.text

    def test_day_cells_are_clickable_to_open_day_view(self, client, mock_api):
        mock_api["get"].return_value = [_event()]

        resp = client.get("/calendar?year=2026&month=7")

        assert resp.status_code == 200
        assert 'hx-get="/calendar/day/2026-07-14"' in resp.text
        assert 'id="calendar-day-modal"' in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.get("/calendar/", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestCalendarDay:
    def test_renders_all_day_and_timed_events_for_day(self, client, mock_api):
        mock_api["get"].return_value = [
            _event(id=1, title="Marriage Anniversary", all_day=True),
            _event(id=2, title="Team sync", start="2026-07-14T09:00:00", end="2026-07-14T09:30:00"),
        ]

        resp = client.get("/calendar/day/2026-07-14")

        assert resp.status_code == 200
        assert "Marriage Anniversary" in resp.text
        assert "Team sync" in resp.text
        assert "09:00" in resp.text
        mock_api["get"].assert_awaited_once_with("/organizer/calendar-events", params={
            "start_from": "2026-07-14T00:00:00",
            "start_to": "2026-07-14T23:59:59",
            "limit": 200,
        })

    def test_renders_empty_state_when_no_events(self, client, mock_api):
        mock_api["get"].return_value = []

        resp = client.get("/calendar/day/2026-07-14")

        assert resp.status_code == 200
        assert "No events this day." in resp.text

    def test_rejects_invalid_date(self, client, mock_api):
        resp = client.get("/calendar/day/not-a-date")

        assert resp.status_code == 200
        assert "Invalid date." in resp.text

    def test_renders_error_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("GET", "http://api/organizer/calendar-events")
        mock_api["get"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.get("/calendar/day/2026-07-14")

        assert resp.status_code == 200
        assert "Could not load events." in resp.text
