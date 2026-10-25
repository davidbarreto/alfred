import httpx

from app.routes.routines import _offset_label, _timing_label


def _step(id=1, title="Prepare dinner", **kw):
    base = {
        "id": id, "routine_id": 1, "position": 0, "title": title, "duration_minutes": 40, "anchor": "start",
        "offset_minutes": -120, "window_start": None, "window_end": None, "context": "home", "location": None,
        "checklist_note_id": None,
    }
    base.update(kw)
    return base


def _routine(id=1, name="Dinner", steps=None, **kw):
    base = {
        "id": id, "name": name, "description": None, "active": True, "recurrence_rule": None, "starts_on": None,
        "steps": steps if steps is not None else [], "event_ids": [],
    }
    base.update(kw)
    return base


def _routes(routines, events=None):
    def fake_get(path, params=None):
        if path == "/organizer/routines":
            return routines
        if path == "/organizer/calendar-events":
            return events if events is not None else []
        raise AssertionError(path)

    return fake_get


class TestLabels:
    def test_offsets_read_naturally(self):
        assert _offset_label("start", -120) == "2 h before the start"
        assert _offset_label("start", -50) == "50 min before the start"
        assert _offset_label("end", 25) == "25 min after the end"
        assert _offset_label("start", -90) == "1 h 30 min before the start"
        assert _offset_label("end", 0) == "at the end"

    def test_window_steps_show_the_window(self):
        step = {"anchor": None, "window_start": "07:30:00", "window_end": "09:00:00"}
        assert _timing_label(step) == "07:30–09:00"


class TestRoutinesPage:
    def test_event_based_routine_with_steps_and_attached_events(self, client, mock_api):
        mock_api["get"].side_effect = _routes(
            [_routine(steps=[_step(), _step(2, "Leave", offset_minutes=-50, duration_minutes=20, context="out", location="Course", checklist_note_id=26)],
                      event_ids=[7])],
            events=[{"id": 7, "title": "Evening class"}, {"id": 8, "title": "Dentist"}],
        )

        resp = client.get("/routines")

        assert resp.status_code == 200
        text = resp.text
        assert "Dinner" in text and "around events" in text
        assert "2 h before the start" in text and "40 min" in text
        assert "50 min before the start" in text and "Course" in text and "checklist note #26" in text
        assert "Evening class" in text
        assert '<option value="8">Dentist</option>' in text

    def test_scheduled_routine_shows_rule_and_windows_and_cannot_be_attached(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_routine(
            2, "Morning", recurrence_rule="FREQ=DAILY", starts_on="2026-10-01",
            steps=[_step(10, "Shower", anchor=None, offset_minutes=None, window_start="07:30:00", window_end="09:00:00", duration_minutes=15)],
        )])

        text = client.get("/routines").text

        assert "scheduled" in text and "FREQ=DAILY" in text and "07:30–09:00" in text
        assert 'data-scheduled="true"' in text
        assert "Attach to an event" not in text

    def test_attached_event_missing_from_the_upcoming_list_still_gets_a_label(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_routine(event_ids=[99])], events=[])
        assert "Event #99" in client.get("/routines").text

    def test_paused_routine_offers_resume(self, client, mock_api):
        mock_api["get"].side_effect = _routes([_routine(active=False)])
        assert "Resume" in client.get("/routines").text

    def test_empty_state(self, client, mock_api):
        mock_api["get"].side_effect = _routes([])
        assert "No routines yet" in client.get("/routines").text

    def test_unreachable_backend_still_renders(self, client, mock_api):
        mock_api["get"].side_effect = httpx.ConnectError("down")
        resp = client.get("/routines")
        assert resp.status_code == 200 and "unavailable" in resp.text

    def test_event_list_failure_only_loses_the_attach_options(self, client, mock_api):
        def fake_get(path, params=None):
            if path == "/organizer/routines":
                return [_routine()]
            raise httpx.ConnectError("down")

        mock_api["get"].side_effect = fake_get
        assert client.get("/routines").status_code == 200

    def test_requires_authentication(self, anon_client):
        assert anon_client.get("/routines", follow_redirects=False).status_code == 302


class TestRoutineWrites:
    def test_create(self, client, mock_api):
        mock_api["post"].return_value = {"id": 3}
        body = {"name": "Morning", "recurrence_rule": "FREQ=DAILY", "starts_on": "2026-10-01"}
        assert client.post("/routines", json=body).json() == {"id": 3}
        mock_api["post"].assert_awaited_once_with("/organizer/routines", json=body)

    def test_update_and_delete(self, client, mock_api):
        mock_api["patch"].return_value = {"id": 3}
        client.patch("/routines/3", json={"active": False})
        mock_api["patch"].assert_awaited_once_with("/organizer/routines/3", json={"active": False})
        resp = client.delete("/routines/3")
        assert resp.json() == {"deleted": True}
        mock_api["delete"].assert_awaited_once_with("/organizer/routines/3")

    def test_step_add_update_delete(self, client, mock_api):
        mock_api["post"].return_value = {"id": 9}
        client.post("/routines/3/steps", json={"title": "Leave", "anchor": "start", "offset_minutes": -50})
        mock_api["post"].assert_awaited_once_with(
            "/organizer/routines/3/steps", json={"title": "Leave", "anchor": "start", "offset_minutes": -50}
        )
        mock_api["patch"].return_value = {"id": 9}
        client.patch("/routines/steps/9", json={"duration_minutes": 30})
        mock_api["patch"].assert_awaited_once_with("/organizer/routines/steps/9", json={"duration_minutes": 30})
        client.delete("/routines/steps/9")
        mock_api["delete"].assert_awaited_once_with("/organizer/routines/steps/9")

    def test_attach_and_detach(self, client, mock_api):
        mock_api["post"].return_value = {"id": 3}
        client.post("/routines/3/events/7")
        mock_api["post"].assert_awaited_once_with("/organizer/routines/3/events/7")
        client.delete("/routines/events/7")
        mock_api["delete"].assert_awaited_once_with("/organizer/routines/events/7")

    def test_backend_rule_violations_are_relayed(self, client, mock_api):
        request = httpx.Request("POST", "http://api/x")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "bad", request=request,
            response=httpx.Response(422, json={"detail": "A scheduled routine cannot be attached to events"}, request=request),
        )
        resp = client.post("/routines/3/events/7")
        assert resp.status_code == 422 and "scheduled routine" in resp.json()["error"]

    def test_taken_position_conflict_is_relayed(self, client, mock_api):
        request = httpx.Request("POST", "http://api/x")
        mock_api["post"].side_effect = httpx.HTTPStatusError(
            "bad", request=request, response=httpx.Response(409, json={"detail": "Position 0 is already used"}, request=request)
        )
        assert client.post("/routines/3/steps", json={"title": "x"}).status_code == 409

    def test_delete_of_unknown_step_is_relayed_as_404(self, client, mock_api):
        request = httpx.Request("DELETE", "http://api/x")
        mock_api["delete"].side_effect = httpx.HTTPStatusError(
            "missing", request=request, response=httpx.Response(404, json={"detail": "Routine step not found"}, request=request)
        )
        assert client.delete("/routines/steps/99").status_code == 404
