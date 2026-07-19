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

    def test_renders_edit_button_per_event(self, client, mock_api):
        mock_api["get"].return_value = [_event(id=7, title="Marriage Anniversary", all_day=True)]

        resp = client.get("/calendar/day/2026-07-14")

        assert resp.status_code == 200
        assert "openEditEvent(" in resp.text
        assert '&#34;id&#34;: 7' in resp.text or '"id": 7' in resp.text

    def test_renders_delete_button_per_event(self, client, mock_api):
        mock_api["get"].return_value = [_event(id=7, title="Marriage Anniversary", all_day=True)]

        resp = client.get("/calendar/day/2026-07-14")

        assert resp.status_code == 200
        assert "deleteEventFromDay(7)" in resp.text


class TestCreateEvent:
    def test_creates_event_without_recurrence(self, client, mock_api):
        mock_api["post"].return_value = _event(id=5, title="Team sync")

        resp = client.post("/calendar/", data={
            "title": "Team sync",
            "start_date": "2026-07-14",
            "start_time": "09:00",
            "end_time": "09:30",
        })

        assert resp.status_code == 204
        mock_api["post"].assert_any_await("/organizer/calendar-events", json={
            "title": "Team sync",
            "start_datetime": "2026-07-14T09:00:00",
            "end_datetime": "2026-07-14T09:30:00",
            "all_day": False,
            "location": None,
            "recurrence_rule": None,
        })

    def test_creates_recurring_event(self, client, mock_api):
        mock_api["post"].return_value = _event(id=5, title="Standup")

        resp = client.post("/calendar/", data={
            "title": "Standup",
            "start_date": "2026-07-14",
            "start_time": "09:00",
            "end_time": "09:15",
            "recurrence_rule": "FREQ=DAILY",
        })

        assert resp.status_code == 204
        mock_api["post"].assert_any_await("/organizer/calendar-events", json={
            "title": "Standup",
            "start_datetime": "2026-07-14T09:00:00",
            "end_datetime": "2026-07-14T09:15:00",
            "all_day": False,
            "location": None,
            "recurrence_rule": "FREQ=DAILY",
        })

    def test_creates_event_with_custom_recurrence_rule(self, client, mock_api):
        mock_api["post"].return_value = _event(id=5, title="Standup")

        resp = client.post("/calendar/", data={
            "title": "Standup",
            "start_date": "2026-07-14",
            "start_time": "09:00",
            "end_time": "09:15",
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10",
        })

        assert resp.status_code == 204
        mock_api["post"].assert_any_await("/organizer/calendar-events", json={
            "title": "Standup",
            "start_datetime": "2026-07-14T09:00:00",
            "end_datetime": "2026-07-14T09:15:00",
            "all_day": False,
            "location": None,
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO,WE,FR;COUNT=10",
        })

    def test_returns_422_when_backend_create_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/calendar-events")
        response = httpx.Response(422, json={"detail": "Invalid event"}, request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError("invalid", request=request, response=response)

        resp = client.post("/calendar/", data={
            "title": "Standup",
            "start_date": "2026-07-14",
        })

        assert resp.status_code == 422
        assert "Invalid event" in resp.text


class TestUpdateEvent:
    def test_updates_timed_event(self, client, mock_api):
        mock_api["patch"].return_value = _event(id=3, title="Team sync")

        resp = client.patch("/calendar/3", data={
            "title": "Team sync",
            "start_date": "2026-07-14",
            "start_time": "09:00",
            "end_time": "09:30",
            "location": "Room 2",
        })

        assert resp.status_code == 204
        mock_api["patch"].assert_any_await("/organizer/calendar-events/3", json={
            "title": "Team sync",
            "start_datetime": "2026-07-14T09:00:00",
            "end_datetime": "2026-07-14T09:30:00",
            "all_day": False,
            "location": "Room 2",
            "recurrence_rule": None,
        })

    def test_updates_all_day_event(self, client, mock_api):
        mock_api["patch"].return_value = _event(id=1, all_day=True)

        resp = client.patch("/calendar/1", data={
            "title": "Marriage Anniversary",
            "start_date": "2026-07-14",
            "all_day": "1",
        })

        assert resp.status_code == 204
        mock_api["patch"].assert_any_await("/organizer/calendar-events/1", json={
            "title": "Marriage Anniversary",
            "start_datetime": "2026-07-14T00:00:00",
            "end_datetime": "2026-07-14T23:59:59",
            "all_day": True,
            "location": None,
            "recurrence_rule": None,
        })

    def test_updates_recurrence_rule(self, client, mock_api):
        mock_api["patch"].return_value = _event(id=3, title="Team sync", tags=["work"])

        resp = client.patch("/calendar/3", data={
            "title": "Team sync",
            "start_date": "2026-07-14",
            "start_time": "09:00",
            "end_time": "09:30",
            "recurrence_rule": "FREQ=WEEKLY",
        })

        assert resp.status_code == 204
        mock_api["patch"].assert_any_await("/organizer/calendar-events/3", json={
            "title": "Team sync",
            "start_datetime": "2026-07-14T09:00:00",
            "end_datetime": "2026-07-14T09:30:00",
            "all_day": False,
            "location": None,
            "recurrence_rule": "FREQ=WEEKLY",
        })

    def test_returns_422_when_backend_update_fails(self, client, mock_api):
        request = httpx.Request("PATCH", "http://api/organizer/calendar-events/3")
        response = httpx.Response(404, json={"detail": "Event not found"}, request=request)
        mock_api["patch"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.patch("/calendar/3", data={
            "title": "Team sync",
            "start_date": "2026-07-14",
        })

        assert resp.status_code == 422
        assert "Event not found" in resp.text


class TestDeleteEvent:
    def test_deletes_event(self, client, mock_api):
        resp = client.delete("/calendar/3")

        assert resp.status_code == 204
        mock_api["delete"].assert_awaited_once_with("/organizer/calendar-events/3")

    def test_returns_422_when_backend_delete_fails(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/organizer/calendar-events/3")
        response = httpx.Response(404, json={"detail": "Event not found"}, request=request)
        mock_api["delete"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.delete("/calendar/3")

        assert resp.status_code == 422
        assert "Event not found" in resp.text

    def test_returns_422_when_backend_unreachable(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/organizer/calendar-events/3")
        mock_api["delete"].side_effect = httpx.ConnectError("connection refused", request=request)

        resp = client.delete("/calendar/3")

        assert resp.status_code == 422
        assert "Failed to delete event." in resp.text
