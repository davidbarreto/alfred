import pytest
import httpx


def _task(id=1, title="Buy milk", status="TODO", priority="LOW", urgency="NORMAL",
          deadline=None, tags=None, recurrence_rule=None):
    return {
        "id": id, "title": title, "status": status, "priority": priority, "urgency": urgency,
        "deadline": deadline, "tags": tags or [], "recurrence_rule": recurrence_rule,
        "is_done_today": False, "is_done_in_cycle": False,
        "streak": None, "total_completions": None, "missed_count": None,
    }


class TestTasksPageFilters:
    def test_today_filter_requests_due_today(self, client, mock_api):
        mock_api["get"].return_value = [_task(id=1)]

        resp = client.get("/tasks/?filter=today")

        assert resp.status_code == 200
        params = mock_api["get"].call_args.kwargs["params"]
        assert params["due_today"] == "true"
        assert "deadline_from" not in params
        assert "deadline_to" not in params

    def test_all_filter_does_not_request_due_today(self, client, mock_api):
        mock_api["get"].return_value = [_task(id=1)]

        resp = client.get("/tasks/?filter=all")

        assert resp.status_code == 200
        params = mock_api["get"].call_args.kwargs["params"]
        assert "due_today" not in params


class TestTaskId:
    def test_row_shows_the_task_id_with_a_tooltip(self, client, mock_api):
        mock_api["get"].return_value = [_task(id=56)]

        text = client.get("/tasks/?filter=all").text

        assert 'title="Task ID 56">#56</span>' in text


class TestRecurrenceFilters:
    def test_habits_filter_keeps_only_recurring_tasks(self, client, mock_api):
        mock_api["get"].side_effect = [[], [
            _task(id=1, title="Water plants", recurrence_rule="FREQ=DAILY"),
            _task(id=2, title="Buy milk", recurrence_rule=None),
        ]]

        resp = client.get("/tasks/?filter=habits")

        assert resp.status_code == 200
        assert "Water plants" in resp.text
        assert "Buy milk" not in resp.text

    def test_one_off_filter_keeps_only_non_recurring_tasks(self, client, mock_api):
        mock_api["get"].side_effect = [[], [
            _task(id=1, title="Water plants", recurrence_rule="FREQ=DAILY"),
            _task(id=2, title="Buy milk", recurrence_rule=None),
        ]]

        resp = client.get("/tasks/?filter=one_off")

        assert resp.status_code == 200
        assert "Buy milk" in resp.text
        assert "Water plants" not in resp.text

    def test_one_off_filter_fetches_full_batch(self, client, mock_api):
        mock_api["get"].return_value = [_task(id=1)]

        resp = client.get("/tasks/?filter=one_off")

        assert resp.status_code == 200
        params = mock_api["get"].call_args.kwargs["params"]
        assert params["limit"] == 200

    def test_all_filter_does_not_apply_recurrence_filtering(self, client, mock_api):
        mock_api["get"].return_value = [
            _task(id=1, title="Water plants", recurrence_rule="FREQ=DAILY"),
            _task(id=2, title="Buy milk", recurrence_rule=None),
        ]

        resp = client.get("/tasks/?filter=all")

        assert resp.status_code == 200
        assert "Water plants" in resp.text
        assert "Buy milk" in resp.text


class TestTagFilters:
    def test_renders_available_tags(self, client, mock_api):
        mock_api["get"].side_effect = [["work", "personal"], [_task(id=1)]]

        resp = client.get("/tasks/?filter=all")

        assert resp.status_code == 200
        assert "work" in resp.text
        assert "personal" in resp.text

    def test_selected_tag_passed_to_api(self, client, mock_api):
        mock_api["get"].side_effect = [["work", "personal"], [_task(id=1)]]

        resp = client.get("/tasks/?filter=all&tag=work")

        assert resp.status_code == 200
        tasks_call = mock_api["get"].call_args_list[-1]
        assert tasks_call.kwargs["params"]["tags"] == ["work"]

    def test_preset_and_selected_tags_are_merged(self, client, mock_api):
        mock_api["get"].side_effect = [["work", "urgent"], [_task(id=1)]]

        resp = client.get("/tasks/?filter=work&tag=urgent")

        assert resp.status_code == 200
        tasks_call = mock_api["get"].call_args_list[-1]
        assert tasks_call.kwargs["params"]["tags"] == ["work", "urgent"]

    def test_active_tag_link_toggles_it_off(self, client, mock_api):
        mock_api["get"].side_effect = [["work"], [_task(id=1)]]

        resp = client.get("/tasks/?filter=all&tag=work")

        assert resp.status_code == 200
        assert 'href="/tasks?filter=all"' in resp.text


class TestUpdateTask:
    def test_updates_task_and_renders_filtered_list(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3, title="Buy oat milk", priority="HIGH")
        mock_api["get"].return_value = [_task(id=3, title="Buy oat milk", priority="HIGH")]

        resp = client.patch("/tasks/3", data={
            "title": "Buy oat milk",
            "priority": "HIGH",
            "urgency": "NORMAL",
            "deadline": "2026-07-20",
            "tags": "groceries, urgent",
            "recurrence_rule": "",
        })

        assert resp.status_code == 200
        assert "Buy oat milk" in resp.text
        mock_api["patch"].assert_any_await("/organizer/tasks/3", json={
            "title": "Buy oat milk",
            "priority": "HIGH",
            "urgency": "NORMAL",
            "tags": ["groceries", "urgent"],
            "deadline": "2026-07-20",
            "recurrence_rule": None,
            "estimate_minutes": None,
            "context": None,
            "available_from": None,
        })

    def test_clearing_deadline_and_recurrence_sends_null(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3)
        mock_api["get"].return_value = [_task(id=3)]

        resp = client.patch("/tasks/3", data={
            "title": "Buy milk",
            "priority": "LOW",
            "urgency": "NORMAL",
            "tags": "",
        })

        assert resp.status_code == 200
        mock_api["patch"].assert_any_await("/organizer/tasks/3", json={
            "title": "Buy milk",
            "priority": "LOW",
            "urgency": "NORMAL",
            "tags": [],
            "deadline": None,
            "recurrence_rule": None,
            "estimate_minutes": None,
            "context": None,
            "available_from": None,
        })

    def test_update_sends_planning_fields(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3)
        mock_api["get"].return_value = [_task(id=3)]

        resp = client.patch("/tasks/3", data={
            "title": "Buy tickets", "tags": "", "estimate_minutes": "10", "context": "phone",
            "available_from": "2026-10-24",
        })

        assert resp.status_code == 200
        payload = mock_api["patch"].await_args.kwargs["json"]
        assert (payload["estimate_minutes"], payload["context"], payload["available_from"]) == (10, "phone", "2026-10-24")

    def test_update_can_clear_planning_fields(self, client, mock_api):
        mock_api["patch"].return_value = _task(id=3)
        mock_api["get"].return_value = [_task(id=3)]

        client.patch("/tasks/3", data={"title": "x", "tags": "", "estimate_minutes": "", "context": ""})

        payload = mock_api["patch"].await_args.kwargs["json"]
        assert (payload["estimate_minutes"], payload["context"]) == (None, None)

    @pytest.mark.parametrize("estimate", ["abc", "0", "-5", "1.5"])
    def test_invalid_estimate_is_rejected_before_calling_the_backend(self, client, mock_api, estimate):
        resp = client.patch("/tasks/3", data={"title": "x", "tags": "", "estimate_minutes": estimate})

        assert resp.status_code == 422
        assert "whole number of minutes" in resp.text
        mock_api["patch"].assert_not_called()

    def test_returns_422_when_backend_update_fails(self, client, mock_api):
        request = httpx.Request("PATCH", "http://api/organizer/tasks/3")
        response = httpx.Response(404, json={"detail": "Task not found"}, request=request)
        mock_api["patch"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.patch("/tasks/3", data={"title": "Buy milk"})

        assert resp.status_code == 422
        assert "Task not found" in resp.text

    def test_requires_authentication(self, anon_client):
        resp = anon_client.patch("/tasks/3", data={"title": "Buy milk"}, follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestSnoozeTask:
    def test_snoozes_and_renders_row(self, client, mock_api):
        mock_api["post"].return_value = {"id": 3, "snoozed_until": "2026-07-21T00:00:00Z"}
        mock_api["get"].return_value = _task(id=3, title="Learn guitar")

        resp = client.post("/tasks/3/snooze")

        assert resp.status_code == 200
        assert "Learn guitar" in resp.text
        assert "Snoozed" in resp.text
        mock_api["post"].assert_any_await("/organizer/tasks/3/snooze")

    def test_returns_422_when_backend_snooze_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/organizer/tasks/3/snooze")
        response = httpx.Response(404, json={"detail": "Task not found"}, request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError("not found", request=request, response=response)

        resp = client.post("/tasks/3/snooze")

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/tasks/3/snooze", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestResetUrgency:
    _RESULT = {"days": 7, "tasks_urgency_reset": 5, "tasks_deadline_moved": 3, "tasks_snoozed": 1}

    def test_resets_and_renders_refreshed_list_with_summary(self, client, mock_api):
        mock_api["post"].return_value = self._RESULT
        mock_api["get"].return_value = [_task(id=3, title="Learn guitar")]

        resp = client.post("/tasks/reset-urgency")

        assert resp.status_code == 200
        assert "Learn guitar" in resp.text
        assert resp.headers["X-Urgency-Reset-Summary"] == (
            "Reset 5 urgent task(s), moved 3 deadline(s), snoozed 1 undated task(s) for 7 days."
        )
        mock_api["post"].assert_awaited_once_with("/core/urgency-reset")

    def test_reloads_list_for_active_filter(self, client, mock_api):
        mock_api["post"].return_value = self._RESULT
        mock_api["get"].return_value = []

        client.post("/tasks/reset-urgency?filter=today")

        params = mock_api["get"].call_args.kwargs["params"]
        assert params["due_today"] == "true"

    def test_returns_422_when_backend_fails(self, client, mock_api):
        request = httpx.Request("POST", "http://api/core/urgency-reset")
        response = httpx.Response(500, request=request)
        mock_api["post"].side_effect = httpx.HTTPStatusError("boom", request=request, response=response)

        resp = client.post("/tasks/reset-urgency")

        assert resp.status_code == 422

    def test_requires_authentication(self, anon_client):
        resp = anon_client.post("/tasks/reset-urgency", follow_redirects=False)

        assert resp.status_code == 302
        assert resp.headers["location"].startswith("/login")


class TestMarkTaskDone:
    def test_passes_occurrence_date_to_backend(self, client, mock_api):
        mock_api["post"].return_value = _task(id=3, recurrence_rule="FREQ=DAILY")

        resp = client.post("/tasks/3/done?occurrence_date=2026-10-04")

        assert resp.status_code == 200
        mock_api["post"].assert_called_once_with("/organizer/tasks/3/complete?occurrence_date=2026-10-04")

    def test_backdate_flag_is_forwarded(self, client, mock_api):
        mock_api["post"].return_value = _task(id=3, recurrence_rule="FREQ=DAILY")

        client.post("/tasks/3/done?occurrence_date=2026-10-04&backdate=true")

        mock_api["post"].assert_called_once_with(
            "/organizer/tasks/3/complete?occurrence_date=2026-10-04&backdate=true"
        )

    def test_without_date_hits_plain_complete(self, client, mock_api):
        mock_api["post"].return_value = _task(id=3)

        client.post("/tasks/3/done")

        mock_api["post"].assert_called_once_with("/organizer/tasks/3/complete")

    def test_backdated_failure_returns_error_status(self, client, mock_api):
        mock_api["post"].side_effect = httpx.HTTPError("boom")

        resp = client.post("/tasks/3/done?occurrence_date=2026-10-04")

        assert resp.status_code == 502


class TestEndRecurringTask:
    def test_cancels_via_backend_and_returns_empty_row(self, client, mock_api):
        mock_api["post"].return_value = _task(id=5, status="CANCELLED", recurrence_rule="FREQ=DAILY")

        resp = client.post("/tasks/5/end")

        assert resp.status_code == 200
        assert resp.text == ""
        mock_api["post"].assert_called_once_with("/organizer/tasks/5/cancel")

    def test_backend_failure_returns_502(self, client, mock_api):
        mock_api["post"].side_effect = httpx.HTTPError("boom")

        assert client.post("/tasks/5/end").status_code == 502


def _completion(id=7, occurrence_date="2026-09-01", completed_at="2026-09-03T12:00:00+00:00"):
    return {"id": id, "task_id": 1, "occurrence_date": occurrence_date, "completed_at": completed_at}


class TestTaskHistoryEditing:
    def test_edit_form_shown_for_selected_completion(self, client, mock_api):
        mock_api["get"].side_effect = [_task(id=1, recurrence_rule="FREQ=MONTHLY"), [_completion()]]

        resp = client.get("/tasks/1/completions/7/edit")

        assert resp.status_code == 200
        assert 'name="occurrence_date"' in resp.text
        assert 'value="2026-09-01"' in resp.text

    def test_plain_history_has_edit_button_and_no_form(self, client, mock_api):
        mock_api["get"].side_effect = [_task(id=1, recurrence_rule="FREQ=MONTHLY"), [_completion()]]

        resp = client.get("/tasks/1/history")

        assert "/tasks/1/completions/7/edit" in resp.text
        assert 'name="occurrence_date"' not in resp.text

    def test_save_patches_backend_and_returns_history(self, client, mock_api):
        mock_api["patch"].return_value = _completion()
        mock_api["get"].side_effect = [_task(id=1, recurrence_rule="FREQ=MONTHLY"), [_completion()]]

        resp = client.patch("/tasks/1/completions/7", data={"occurrence_date": "2026-08-01", "completed_on": "2026-09-02"})

        assert resp.status_code == 200
        mock_api["patch"].assert_called_once_with(
            "/organizer/tasks/1/completions/7",
            json={"occurrence_date": "2026-08-01", "completed_on": "2026-09-02"},
        )

    def test_backend_conflict_rerenders_edit_form_with_reason(self, client, mock_api):
        request = httpx.Request("PATCH", "http://api/x")
        response = httpx.Response(409, json={"detail": "A completion already exists for 2026-08-01."}, request=request)
        mock_api["patch"].side_effect = httpx.HTTPStatusError("conflict", request=request, response=response)
        mock_api["get"].side_effect = [_task(id=1, recurrence_rule="FREQ=MONTHLY"), [_completion()]]

        resp = client.patch("/tasks/1/completions/7", data={"occurrence_date": "2026-08-01", "completed_on": "2026-09-02"})

        assert resp.status_code == 200
        assert "already exists" in resp.text
        assert 'name="occurrence_date"' in resp.text


class TestCreateTaskPlanningFields:
    def test_create_sends_only_the_planning_fields_that_are_set(self, client, mock_api):
        mock_api["post"].return_value = _task(id=9)
        mock_api["get"].return_value = [_task(id=9)]

        client.post("/tasks/", data={"title": "Buy tickets", "estimate_minutes": "10", "context": "phone"})

        payload = mock_api["post"].await_args.kwargs["json"]
        assert payload["estimate_minutes"] == 10 and payload["context"] == "phone"
        assert "available_from" not in payload

    def test_create_without_planning_fields_leaves_them_out(self, client, mock_api):
        mock_api["post"].return_value = _task(id=9)
        mock_api["get"].return_value = [_task(id=9)]

        client.post("/tasks/", data={"title": "Plain"})

        payload = mock_api["post"].await_args.kwargs["json"]
        assert not {"estimate_minutes", "context", "available_from"} & set(payload)

    def test_create_rejects_a_bad_estimate(self, client, mock_api):
        resp = client.post("/tasks/", data={"title": "x", "estimate_minutes": "soon"})
        assert resp.status_code == 422
        mock_api["post"].assert_not_called()


class TestTaskRowPlanningDisplay:
    def test_row_shows_estimate_and_context_when_set(self, client, mock_api):
        mock_api["get"].return_value = [{**_task(id=4, title="Call bank"), "estimate_minutes": 15, "context": "phone"}]
        resp = client.get("/tasks")
        assert "15 min · phone" in resp.text

    def test_row_hides_the_marker_without_planning_fields(self, client, mock_api):
        mock_api["get"].return_value = [_task(id=4, title="Call bank")]
        assert "ti-clock" not in client.get("/tasks").text.split("Call bank")[1].split("</li>")[0]
